from __future__ import annotations

import argparse
import os
import secrets
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
import paho.mqtt.client as mqtt

from config import (
    CLOUD_MODEL_PATH,
    CLOUD_URL,
    EDGE_MODEL_PATH,
    MQTT_HOST,
    MQTT_PORT,
    VIBRATION_EDGE_ID,
    VIBRATION_MODEL_PATH,
)


ROOT = Path(__file__).resolve().parent
ULTRALYTICS_CONFIG_DIR = ROOT / ".runtime" / "ultralytics"


def start(module: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-u", "-m", module],
        cwd=ROOT,
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


def webots_executable() -> Path:
    configured = os.getenv("PERIMETER_WEBOTS_EXE") or shutil.which("webots")
    if configured:
        return Path(configured)
    home = Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Webots"
    candidates = [home / "webots.exe", *home.glob("msys64/*/bin/webots.exe")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Webots was not found. Set PERIMETER_WEBOTS_EXE to its executable path.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webots", action="store_true", help="Run the edge and gateway in Webots")
    args = parser.parse_args()
    ULTRALYTICS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(ULTRALYTICS_CONFIG_DIR))
    simulator = webots_executable() if args.webots else None
    os.environ["PERIMETER_WEBOTS_MODE"] = "1" if simulator else "0"
    required_models = [EDGE_MODEL_PATH, CLOUD_MODEL_PATH]
    if simulator:
        required_models.append(VIBRATION_MODEL_PATH)
    missing = [path.name for path in required_models if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing pretrained model weights: {', '.join(missing)}")

    processes: list[subprocess.Popen[bytes]] = []
    try:
        processes.append(start("broker.app"))
        wait_for_mqtt(MQTT_HOST, MQTT_PORT)

        processes.append(start("cloud.app"))
        wait_for_api("/api/health")

        if simulator:
            os.environ["PERIMETER_NWK_SKEY"] = secrets.token_hex(16)
            os.environ["PERIMETER_APP_SKEY"] = secrets.token_hex(16)
            os.environ["PERIMETER_VIBRATION_NWK_SKEY"] = secrets.token_hex(16)
            os.environ["PERIMETER_VIBRATION_APP_SKEY"] = secrets.token_hex(16)
            processes.append(start("gateway.network_server"))
            environment = os.environ.copy()
            environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
            processes.append(subprocess.Popen(
                [str(simulator), "--batch", "--stdout", "--stderr", "--mode=realtime", str(ROOT / "webots/worlds/perimeter.wbt")],
                cwd=ROOT,
                env=environment,
            ))
        else:
            processes.append(start("edge.app"))
        deadline = time.monotonic() + (150 if simulator else 30)
        while time.monotonic() < deadline:
            status = wait_for_api("/api/status")
            camera_online = (status.get("edge") or {}).get("status") == "online"
            vibration_online = (status.get("vibration_edge") or {}).get("status") == "online"
            if camera_online and (not simulator or vibration_online):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("YOLO11n edge worker did not come online")

        print("\nRGB object-detection demo is running.")
        print(f"Dashboard:   {CLOUD_URL}")
        print(f"MQTT broker: {MQTT_HOST}:{MQTT_PORT}")
        edge_name = "simulated Jetson Nano in Webots" if simulator else "logical edge"
        print(f"Edge model:  YOLO11n ({edge_name}, executed on laptop CPU)")
        if simulator:
            print("Sensor edge: Tiny 1D CNN (512 MB low-power profile, laptop CPU)")
        print("Cloud model: YOLO11m (laptop CPU)")
        print("Press Ctrl+C here to stop.\n")

        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("One of the demo processes stopped unexpectedly")
    except KeyboardInterrupt:
        print("\nStopping demo...")
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
