from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CLOUD_HOST = os.getenv("PERIMETER_CLOUD_HOST", "127.0.0.1")
CLOUD_PORT = int(os.getenv("PERIMETER_CLOUD_PORT", "8000"))
CLOUD_URL = f"http://{CLOUD_HOST}:{CLOUD_PORT}"

MQTT_HOST = os.getenv("PERIMETER_MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("PERIMETER_MQTT_PORT", "1883"))
MQTT_QOS = 1
MQTT_KEEPALIVE = 30
SENSOR_TOPIC = "perimeter/camera/+/image"
EDGE_RESULT_TOPIC = "perimeter/edge/+/result"
STATUS_TOPIC = "perimeter/status/+/state"
ALERT_TOPIC = "perimeter/alerts"

EDGE_ID = "simulated-edge-01"
VIBRATION_EDGE_ID = "vibration-edge-01"
PERIMETER_ZONE = "north-gate"
EDGE_MODEL_PATH = BASE_DIR / "yolo11n.pt"
CLOUD_MODEL_PATH = BASE_DIR / "yolo11m.pt"
VIBRATION_MODEL_PATH = BASE_DIR / "vibration" / "tiny_vibration_cnn.pt"
DATABASE_PATH = BASE_DIR / "perimeter_events.db"
CAMERA_LORAWAN_DEVICE = "da1b0126"
VIBRATION_LORAWAN_DEVICE = "da1b0226"

JETSON_NANO_PROFILE = {
    "device": "NVIDIA Jetson Nano",
    "simulation": "Webots functional simulation",
    "execution_host": "Windows laptop CPU",
    "cpu_profile": "Quad-core ARM Cortex-A57",
    "gpu_profile": "128-core NVIDIA Maxwell",
    "memory_mb": 4096,
    "power_mode_w": 10,
}

VIBRATION_EDGE_PROFILE = {
    "device": "Low-power vibration edge",
    "simulation": "Webots functional simulation",
    "execution_host": "Windows laptop CPU",
    "cpu_profile": "Low-power quad-core ARM profile",
    "memory_mb": 512,
    "power_mode_w": 2,
}

DEMO_IMAGES = {
    "sample_01": {
        "file": "demo_normal.jpg",
        "title": "Sample 01",
        "description": "Offline RGB test image",
    },
    "sample_02": {
        "file": "demo_animal.jpg",
        "title": "Sample 02",
        "description": "Offline RGB test image",
    },
    "sample_03": {
        "file": "demo_person.jpg",
        "title": "Sample 03",
        "description": "Offline RGB test image",
    },
    "sample_04": {
        "file": "demo_vehicle.jpg",
        "title": "Sample 04",
        "description": "Offline RGB test image",
    },
    "sample_05": {
        "file": "demo_coco_009.jpg",
        "title": "Sample 05",
        "description": "Offline RGB test image",
    },
    "sample_06": {
        "file": "demo_coco_034.jpg",
        "title": "Sample 06",
        "description": "Offline RGB test image",
    },
    "sample_07": {
        "file": "demo_coco_042.jpg",
        "title": "Sample 07",
        "description": "Offline RGB test image",
    },
    "sample_08": {
        "file": "demo_coco_049.jpg",
        "title": "Sample 08",
        "description": "Offline RGB test image",
    },
    "sample_09": {
        "file": "demo_coco_061.jpg",
        "title": "Sample 09",
        "description": "Offline RGB test image",
    },
}

PERSON_CLASSES = {"person"}
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
ANIMAL_CLASSES = {
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"
}
SECURITY_CLASSES = PERSON_CLASSES | VEHICLE_CLASSES | ANIMAL_CLASSES


def sensor_topic(camera_id: str) -> str:
    return f"perimeter/camera/{camera_id}/image"


def edge_topic(edge_id: str = EDGE_ID) -> str:
    return f"perimeter/edge/{edge_id}/result"


def status_topic(component_id: str) -> str:
    return f"perimeter/status/{component_id}/state"
