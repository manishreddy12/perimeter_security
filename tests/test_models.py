from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paho.mqtt.client as mqtt
import torch

import cloud.app as cloud_app
from config import (
    BASE_DIR,
    CLOUD_MODEL_PATH,
    DEMO_IMAGES,
    EDGE_MODEL_PATH,
    JETSON_NANO_PROFILE,
    PERIMETER_ZONE,
    VIBRATION_EDGE_ID,
    VIBRATION_EDGE_PROFILE,
    VIBRATION_MODEL_PATH,
    edge_topic,
    sensor_topic,
)
from edge.app import choose_location, summarize
from run_demo import WEBOTS_WORLDS
from vibration.model import CLASS_NAMES, WINDOW_SIZE, TinyVibrationCNN, parameter_count


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
            self.assertEqual(event["zone"], PERIMETER_ZONE)
        finally:
            cloud_app.mqtt_client = None
            cloud_app.broker_connected.clear()

    def test_cloud_schema_stores_zone_for_both_edge_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "events.db"
            with patch.object(cloud_app, "DATABASE_PATH", database):
                cloud_app.initialize_database()
                stored_vibration = cloud_app.insert_vibration_event(
                    {
                        "event_id": "vibration-zone-test",
                        "edge_id": VIBRATION_EDGE_ID,
                        "classification": "normal",
                        "confidence": 0.9,
                        "rms_g": 0.01,
                        "peak_g": 0.02,
                        "latency_ms": 0.5,
                        "model": "Tiny 1D CNN",
                        "model_parameters": 482,
                        "sample_rate_hz": 31.25,
                        "window_samples": 64,
                        "resource_profile": VIBRATION_EDGE_PROFILE,
                    }
                )
                connection = sqlite3.connect(database)
                try:
                    camera_columns = {
                        row[1] for row in connection.execute("PRAGMA table_info(events)")
                    }
                    vibration_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(vibration_events)")
                    }
                finally:
                    connection.close()
            self.assertIn("zone", camera_columns)
            self.assertIn("zone", vibration_columns)
            self.assertEqual(stored_vibration["zone"], PERIMETER_ZONE)

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

    def test_jetson_profile_is_explicitly_simulated(self) -> None:
        self.assertEqual(JETSON_NANO_PROFILE["device"], "NVIDIA Jetson Nano")
        self.assertEqual(JETSON_NANO_PROFILE["execution_host"], "Windows laptop CPU")
        self.assertIn("simulation", str(JETSON_NANO_PROFILE["simulation"]).lower())

    def test_vibration_edge_model_and_resource_profile(self) -> None:
        self.assertTrue(VIBRATION_MODEL_PATH.exists())
        model = TinyVibrationCNN()
        model.load_state_dict(torch.load(VIBRATION_MODEL_PATH, map_location="cpu", weights_only=True))
        output = model(torch.zeros(1, 1, WINDOW_SIZE))
        self.assertEqual(tuple(output.shape), (1, len(CLASS_NAMES)))
        self.assertLess(parameter_count(model), 1_000)
        self.assertEqual(VIBRATION_EDGE_PROFILE["memory_mb"], 512)
        self.assertEqual(JETSON_NANO_PROFILE["memory_mb"], 4096)

    def test_each_edge_has_a_separate_webots_world(self) -> None:
        self.assertEqual(len(WEBOTS_WORLDS), 2)
        camera_world, vibration_world = WEBOTS_WORLDS
        self.assertTrue(camera_world.exists())
        self.assertTrue(vibration_world.exists())
        camera_text = camera_world.read_text(encoding="utf-8")
        vibration_text = vibration_world.read_text(encoding="utf-8")
        self.assertIn('controller "camera_edge"', camera_text)
        self.assertNotIn('controller "vibration_edge"', camera_text)
        self.assertIn('controller "vibration_edge"', vibration_text)
        self.assertNotIn('controller "camera_edge"', vibration_text)
        self.assertIn('controller "perimeter_gateway"', camera_text)
        self.assertIn('controller "perimeter_gateway"', vibration_text)
        shared_fence = 'translation 3 0 1\n  name "North Gate monitored fence"'
        self.assertIn(shared_fence, camera_text)
        self.assertIn(shared_fence, vibration_text)
        self.assertIn('translation 2.82 -0.75 0.8', camera_text)
        self.assertIn('translation 2.82 -0.75 0.8', vibration_text)


if __name__ == "__main__":
    unittest.main()
