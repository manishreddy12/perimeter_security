from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests
import paho.mqtt.client as mqtt

from config import CLOUD_MODEL_PATH, CLOUD_URL, EDGE_MODEL_PATH, MQTT_HOST, MQTT_PORT


ROOT = Path(__file__).resolve().parent
WINDOWS_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0


def start(module: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-u", "-m", module],
        cwd=ROOT,
        creationflags=WINDOWS_PROCESS_GROUP,
    )


def wait_for_mqtt(host: str, port: int, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
        try:
            client.connect(host, port, keepalive=5)
            client.disconnect()
            return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"MQTT broker {host}:{port} did not become ready")


def wait_for_api(path: str, timeout: float = 60) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{CLOUD_URL}{path}", timeout=1)
            if response.ok:
                return response.json()
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise RuntimeError(f"Cloud API {path} did not become ready")


def main() -> None:
    missing = [path.name for path in (EDGE_MODEL_PATH, CLOUD_MODEL_PATH) if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing pretrained model weights: {', '.join(missing)}")

    processes: list[subprocess.Popen[bytes]] = []
    try:
        processes.append(start("broker.app"))
        wait_for_mqtt(MQTT_HOST, MQTT_PORT)

        processes.append(start("cloud.app"))
        wait_for_api("/api/health")

        processes.append(start("edge.app"))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if (wait_for_api("/api/status").get("edge") or {}).get("status") == "online":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("YOLO11n edge worker did not come online")

        print("\nRGB object-detection demo is running.")
        print(f"Dashboard:   {CLOUD_URL}")
        print(f"MQTT broker: {MQTT_HOST}:{MQTT_PORT}")
        print("Edge model:  YOLO11n (simulated edge on CPU)")
        print("Cloud model: YOLO11m (laptop CPU)")
        print("Press Ctrl+C here to stop.\n")

        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("One of the demo processes stopped unexpectedly")
    except KeyboardInterrupt:
        print("\nStopping demo...")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
