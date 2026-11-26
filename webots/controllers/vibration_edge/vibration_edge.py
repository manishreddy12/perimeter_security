from __future__ import annotations

import json
import math
import sys
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from controller import Robot

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import paho.mqtt.client as mqtt
import torch

from config import (
    MQTT_HOST,
    MQTT_KEEPALIVE,
    MQTT_PORT,
    MQTT_QOS,
    PERIMETER_ZONE,
    VIBRATION_EDGE_ID,
    VIBRATION_EDGE_PROFILE,
    VIBRATION_LORAWAN_DEVICE,
    VIBRATION_MODEL_PATH,
    status_topic,
)
from gateway.radio import UplinkEncoder
from vibration.model import CLASS_NAMES, SAMPLE_RATE_HZ, WINDOW_SIZE, TinyVibrationCNN, parameter_count
from vibration.payload import encode_vibration_event


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def status(state: str, processed: int, model: TinyVibrationCNN) -> dict[str, object]:
    return {
        "status": state,
        "component": "edge",
        "edge_id": VIBRATION_EDGE_ID,
        "source": "webots-vibration-sensor",
        "device": VIBRATION_EDGE_PROFILE["device"],
        "model": "Tiny 1D CNN",
        "model_parameters": parameter_count(model),
        "runtime": VIBRATION_EDGE_PROFILE["simulation"],
        "execution_host": VIBRATION_EDGE_PROFILE["execution_host"],
        "device_profile": VIBRATION_EDGE_PROFILE,
        "events_processed": processed,
        "timestamp": now_iso(),
    }


def main() -> None:
    torch.set_num_threads(1)
    model = TinyVibrationCNN()
    model.load_state_dict(torch.load(VIBRATION_MODEL_PATH, map_location="cpu", weights_only=True))
    model.eval()

    robot = Robot()
    timestep = int(robot.getBasicTimeStep())
    keyboard = robot.getKeyboard()
    keyboard.enable(timestep)
    emitter = robot.getDevice("uplink")
    encoder = UplinkEncoder(
        VIBRATION_LORAWAN_DEVICE,
        "PERIMETER_VIBRATION_NWK_SKEY",
        "PERIMETER_VIBRATION_APP_SKEY",
    )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=VIBRATION_EDGE_ID,
        protocol=mqtt.MQTTv311,
    )
    processed = 0
    client.will_set(
        status_topic(VIBRATION_EDGE_ID),
        json.dumps(status("offline", processed, model)),
        qos=MQTT_QOS,
        retain=True,
    )
    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
    client.loop_start()
    client.publish(
        status_topic(VIBRATION_EDGE_ID),
        json.dumps(status("online", processed, model)),
        qos=MQTT_QOS,
        retain=True,
    )

    samples: deque[float] = deque(maxlen=WINDOW_SIZE)
    radio_frames: deque[bytes] = deque()
    window_index = 0
    injecting = False
    force_next_window = False
    rng = np.random.default_rng(2026)
    print(
        f"[vibration-edge] Tiny 1D CNN ready: {parameter_count(model)} parameters, "
        f"{VIBRATION_EDGE_PROFILE['memory_mb']} MB profile",
        flush=True,
    )
    try:
        while robot.step(timestep) != -1:
            if radio_frames:
                radio_frame = radio_frames.popleft()
                emitter.send(radio_frame)
            if keyboard.getKey() == ord("V"):
                force_next_window = True
                injecting = True
            if not samples:
                injecting = force_next_window or window_index % 4 == 3
                force_next_window = False

            centered = float(rng.normal(0.0, 0.01))
            if injecting:
                centered += 0.55 * math.sin(2 * math.pi * 8.0 * len(samples) / SAMPLE_RATE_HZ)
            samples.append(centered)
            if len(samples) < WINDOW_SIZE:
                continue

            signal = np.asarray(samples, dtype=np.float32)
            signal -= signal.mean()
            tensor = torch.from_numpy(signal).view(1, 1, WINDOW_SIZE)
            started = time.perf_counter()
            with torch.no_grad():
                probabilities = torch.softmax(model(tensor), dim=1)[0]
            latency_ms = (time.perf_counter() - started) * 1000.0
            class_index = int(probabilities.argmax())
            classification = CLASS_NAMES[class_index]
            event = {
                "event_type": "vibration",
                "event_id": str(uuid.uuid4()),
                "timestamp": now_iso(),
                "edge_id": VIBRATION_EDGE_ID,
                "zone": PERIMETER_ZONE,
                "classification": classification,
                "confidence": round(float(probabilities[class_index]), 4),
                "rms_g": round(float(np.sqrt(np.mean(signal ** 2))), 4),
                "peak_g": round(float(np.max(np.abs(signal))), 4),
                "latency_ms": round(latency_ms, 3),
                "model": "Tiny 1D CNN",
                "model_parameters": parameter_count(model),
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "window_samples": WINDOW_SIZE,
                "resource_profile": VIBRATION_EDGE_PROFILE,
            }
            application_payload = encode_vibration_event(event)
            encoded_frames = list(encoder.encode_bytes(application_payload))
            radio_frames.extend(encoded_frames)
            print(
                f"[lorawan-tx][edge-2] zone={PERIMETER_ZONE} "
                f"devaddr={VIBRATION_LORAWAN_DEVICE.upper()} "
                f"event={event['event_id'][:8]} payload={len(application_payload)}B "
                f"fragments={len(encoded_frames)}",
                flush=True,
            )
            print(
                f"[lorawan-payload][edge-2] anomaly="
                f"{'YES' if classification == 'vibration_anomaly' else 'NO'} "
                f"confidence={event['confidence']:.1%} rms={event['rms_g']:.4f}g "
                f"peak={event['peak_g']:.4f}g compact_hex={application_payload.hex().upper()}",
                flush=True,
            )
            processed += 1
            client.publish(
                status_topic(VIBRATION_EDGE_ID),
                json.dumps(status("online", processed, model)),
                qos=MQTT_QOS,
                retain=True,
            )
            print(
                f"[vibration-edge] window {window_index + 1} -> {classification} "
                f"({event['confidence']:.0%}, {latency_ms:.2f} ms)",
                flush=True,
            )
            samples.clear()
            window_index += 1
    finally:
        client.publish(
            status_topic(VIBRATION_EDGE_ID),
            json.dumps(status("offline", processed, model)),
            qos=MQTT_QOS,
            retain=True,
        )
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
