import sys
from pathlib import Path
from queue import Empty, Queue

from controller import Robot

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import cv2
import numpy as np
import requests

from config import CLOUD_URL, JETSON_NANO_PROFILE, MQTT_HOST, MQTT_PORT
from edge.app import EdgeService
from gateway.radio import UplinkEncoder


def main():
    robot = Robot()
    timestep = int(robot.getBasicTimeStep())
    camera = robot.getDevice("camera")
    camera.enable(timestep)
    position = robot.getDevice("position")
    position.enable(timestep)
    keyboard = robot.getKeyboard()
    keyboard.enable(timestep)
    emitter = robot.getDevice("uplink")
    outgoing = Queue()
    encoder = UplinkEncoder()
    service = EdgeService(
        MQTT_HOST,
        MQTT_PORT,
        "webots-jetson-nano",
        publish_result=outgoing.put,
        device_profile=JETSON_NANO_PROFILE,
    )
    service.client.loop_start()
    capture_pressed = False
    initial_capture = True
    try:
        while robot.step(timestep) != -1:
            pressed = keyboard.getKey() == ord("C")
            if (initial_capture or (pressed and not capture_pressed)) and service.connected.is_set():
                initial_capture = False
                frame = np.frombuffer(camera.getImage(), dtype=np.uint8)
                frame = frame.reshape(camera.getHeight(), camera.getWidth(), 4)
                image = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                success, jpeg = cv2.imencode(".jpg", image)
                if success:
                    try:
                        response = requests.post(
                            f"{CLOUD_URL}/api/webots/capture",
                            files={"image": ("webots-camera.jpg", jpeg.tobytes(), "image/jpeg")},
                            timeout=5,
                        )
                        response.raise_for_status()
                        event = response.json()
                        event["sensor_readings"] = {
                            "position_m": position.getValues(),
                            "edge_device": JETSON_NANO_PROFILE["device"],
                            "simulated_power_mode_w": JETSON_NANO_PROFILE["power_mode_w"],
                            "simulated_memory_mb": JETSON_NANO_PROFILE["memory_mb"],
                        }
                        service.report_result(event, service.model.predict_frame(image))
                    except requests.RequestException as exc:
                        print(f"[edge] camera capture failed: {exc}", flush=True)
            capture_pressed = pressed
            try:
                result = outgoing.get_nowait()
            except Empty:
                continue
            try:
                for frame in encoder.encode(result):
                    emitter.send(frame)
            except ValueError as exc:
                print(f"[edge] could not send uplink: {exc}", flush=True)
    finally:
        service.publish_status("offline")
        service.client.disconnect()
        service.client.loop_stop()


if __name__ == "__main__":
    main()
