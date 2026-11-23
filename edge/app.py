from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime, timezone

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests
from ultralytics import YOLO

from config import (
    ANIMAL_CLASSES,
    EDGE_ID,
    EDGE_MODEL_PATH,
    MQTT_HOST,
    MQTT_KEEPALIVE,
    MQTT_PORT,
    MQTT_QOS,
    PERSON_CLASSES,
    SECURITY_CLASSES,
    SENSOR_TOPIC,
    VEHICLE_CLASSES,
    edge_topic,
    status_topic,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_image(image_url: str) -> np.ndarray:
    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    image = cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not decode image from {image_url}")
    return image


def security_detections(result) -> list[dict[str, object]]:
    detections: list[dict[str, object]] = []
    if result.boxes is None:
        return detections
    for box in result.boxes:
        class_name = str(result.names[int(box.cls.item())])
        if class_name not in SECURITY_CLASSES:
            continue
        detections.append(
            {
                "class": class_name,
                "confidence": round(float(box.conf.item()), 4),
                "bbox": [round(float(value), 1) for value in box.xyxy[0].tolist()],
            }
        )
    return detections


def summarize(detections: list[dict[str, object]]) -> str:
    classes = {str(item["class"]) for item in detections}
    if classes & VEHICLE_CLASSES:
        return "vehicle"
    if classes & PERSON_CLASSES:
        return "person"
    if classes & ANIMAL_CLASSES:
        return "animal"
    return "normal"


def choose_location(summary: str, detections: list[dict[str, object]]) -> tuple[str, str]:
    if summary in {"person", "vehicle"}:
        return "cloud", f"{summary} is security-sensitive and needs stronger verification"
    if detections and max(float(item["confidence"]) for item in detections) < 0.50:
        return "cloud", "edge detections have low confidence"
    return "edge", "edge result is sufficient for this event"


class EdgeVisionModel:
    def __init__(self) -> None:
        print(f"[edge] loading YOLO11n from {EDGE_MODEL_PATH.name}", flush=True)
        self.model = YOLO(str(EDGE_MODEL_PATH))
        self.inference_lock = threading.Lock()

    def predict(self, image_url: str) -> dict[str, object]:
        return self.predict_frame(load_image(image_url))

    def predict_frame(self, image: np.ndarray) -> dict[str, object]:
        with self.inference_lock:
            started = time.perf_counter()
            result = self.model.predict(image, imgsz=416, conf=0.25, device="cpu", verbose=False)[0]
            latency_ms = (time.perf_counter() - started) * 1000.0
        detections = security_detections(result)
        return {
            "summary": summarize(detections),
            "detections": detections,
            "latency_ms": round(latency_ms, 2),
            "model": "YOLO11n",
            "input_size": 416,
        }


class EdgeService:
    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        source: str,
        publish_result=None,
        device_profile: dict[str, object] | None = None,
    ) -> None:
        self.source = source
        self.publish_result = publish_result
        self.device_profile = device_profile or {
            "device": "Logical edge service",
            "simulation": "Python process",
            "execution_host": "Windows laptop CPU",
        }
        self.model = EdgeVisionModel()
        self.processed = 0
        self.connected = threading.Event()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{EDGE_ID}-{source}",
            protocol=mqtt.MQTTv311,
        )
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.will_set(
            status_topic(EDGE_ID), json.dumps(self.status("offline")), qos=MQTT_QOS, retain=True
        )
        self.client.connect_async(broker_host, broker_port, MQTT_KEEPALIVE)

    def status(self, state: str) -> dict[str, object]:
        return {
            "status": state,
            "component": "edge",
            "edge_id": EDGE_ID,
            "source": self.source,
            "model": "YOLO11n",
            "device": self.device_profile["device"],
            "runtime": self.device_profile["simulation"],
            "execution_host": self.device_profile["execution_host"],
            "device_profile": self.device_profile,
            "events_processed": self.processed,
            "timestamp": now_iso(),
        }

    def publish_status(self, state: str = "online") -> None:
        self.client.publish(
            status_topic(EDGE_ID), json.dumps(self.status(state)), qos=MQTT_QOS, retain=True
        )

    def on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            self.connected.set()
            client.subscribe(SENSOR_TOPIC, qos=MQTT_QOS)
            self.publish_status()
            print(f"[edge] YOLO11n subscribed to {SENSOR_TOPIC}", flush=True)

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self.connected.clear()

    def on_message(self, client, userdata, message) -> None:
        try:
            event = json.loads(message.payload.decode("utf-8"))
            if "image_url" not in event or "event_id" not in event:
                print(f"[edge] ignored malformed camera event on {message.topic}", flush=True)
                return
            prediction = self.model.predict(str(event["image_url"]))
            self.report_result(event, prediction)
        except Exception as exc:
            print(f"[edge] failed to process image event: {exc}", flush=True)

    def report_result(self, event, prediction) -> None:
        location, reason = choose_location(str(prediction["summary"]), prediction["detections"])
        result = {
            "event_id": event["event_id"],
            "timestamp": now_iso(),
            "camera_event": event,
            "edge_result": prediction,
            "offload": {"selected_location": location, "reason": reason},
            "edge_runtime": self.status("online"),
        }
        if self.publish_result is None:
            self.client.publish(edge_topic(), json.dumps(result), qos=MQTT_QOS)
        else:
            self.publish_result(result)
        self.processed += 1
        self.publish_status()
        print(
            f"[edge] {event['image_name']} -> {prediction['summary']} -> {location} "
            f"({prediction['latency_ms']:.0f} ms)",
            flush=True,
        )

    def run(self) -> None:
        self.client.loop_start()
        if not self.connected.wait(10):
            raise RuntimeError("Edge could not connect to the MQTT broker")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.publish_status("offline")
            self.client.disconnect()
            self.client.loop_stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the simulated YOLO edge worker")
    parser.add_argument("--broker-host", default=MQTT_HOST)
    parser.add_argument("--broker-port", type=int, default=MQTT_PORT)
    parser.add_argument("--source", default="simulated-edge")
    args = parser.parse_args()
    EdgeService(args.broker_host, args.broker_port, args.source).run()


if __name__ == "__main__":
    main()
