from __future__ import annotations

import io
import json
import unittest

import paho.mqtt.client as mqtt

import cloud.app as cloud_app
from config import BASE_DIR, CLOUD_MODEL_PATH, DEMO_IMAGES, EDGE_MODEL_PATH, edge_topic, sensor_topic
from edge.app import choose_location, summarize


class FakePublishInfo:
    rc = mqtt.MQTT_ERR_SUCCESS


class FakeMqttClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def publish(self, topic, payload, qos=0):
        self.messages.append((topic, payload))
        return FakePublishInfo()


class DemoTests(unittest.TestCase):
    def test_model_weights_exist(self) -> None:
        self.assertTrue(EDGE_MODEL_PATH.exists())
        self.assertTrue(CLOUD_MODEL_PATH.exists())

    def test_demo_images_exist(self) -> None:
        self.assertEqual(len(DEMO_IMAGES), 9)
        for image in DEMO_IMAGES.values():
            with self.subTest(image=image["file"]):
                self.assertTrue((BASE_DIR / "cloud" / "static" / image["file"]).exists())

    def test_sample_event_has_no_answer_tag(self) -> None:
        fake = FakeMqttClient()
        cloud_app.mqtt_client = fake
        cloud_app.broker_connected.set()
        try:
            response = cloud_app.app.test_client().post("/api/run", json={"image": "sample_01"})
            self.assertEqual(response.status_code, 202)
            event = json.loads(fake.messages[-1][1])
            self.assertNotIn("expected_label", event)
            self.assertEqual(event["source"], "sample")
        finally:
            cloud_app.mqtt_client = None
            cloud_app.broker_connected.clear()

    def test_image_upload_publishes_without_answer_tag(self) -> None:
        fake = FakeMqttClient()
        cloud_app.mqtt_client = fake
        cloud_app.broker_connected.set()
        image_bytes = (BASE_DIR / "cloud" / "static" / "demo_person.jpg").read_bytes()
        try:
            response = cloud_app.app.test_client().post(
                "/api/upload",
                data={"image": (io.BytesIO(image_bytes), "my-photo.jpg")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 202)
            event = json.loads(fake.messages[-1][1])
            self.assertNotIn("expected_label", event)
            self.assertEqual(event["source"], "upload")
            self.assertEqual(event["image_name"], "my-photo.jpg")
        finally:
            cloud_app.mqtt_client = None
            cloud_app.broker_connected.clear()
            cloud_app.uploaded_images.clear()

    def test_security_summary(self) -> None:
        self.assertEqual(summarize([]), "normal")
        self.assertEqual(summarize([{"class": "dog"}]), "animal")
        self.assertEqual(summarize([{"class": "person"}]), "person")
        self.assertEqual(summarize([{"class": "bus"}]), "vehicle")

    def test_offload_policy(self) -> None:
        self.assertEqual(choose_location("person", [])[0], "cloud")
        self.assertEqual(choose_location("vehicle", [])[0], "cloud")
        self.assertEqual(choose_location("animal", [{"confidence": 0.8}])[0], "edge")

    def test_topics(self) -> None:
        self.assertEqual(sensor_topic("cam-1"), "perimeter/camera/cam-1/image")
        self.assertEqual(edge_topic("edge-1"), "perimeter/edge/edge-1/result")


if __name__ == "__main__":
    unittest.main()
