from __future__ import annotations

import struct
import uuid
from datetime import datetime, timezone

from config import VIBRATION_EDGE_ID, VIBRATION_EDGE_PROFILE
from vibration.model import CLASS_NAMES, SAMPLE_RATE_HZ, WINDOW_SIZE, TinyVibrationCNN, parameter_count


PAYLOAD_FORMAT = "<16sIBHHHH"
PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FORMAT)
MODEL_PARAMETERS = parameter_count(TinyVibrationCNN())


def encode_vibration_event(event: dict[str, object]) -> bytes:
    return struct.pack(
        PAYLOAD_FORMAT,
        uuid.UUID(str(event["event_id"])).bytes,
        int(datetime.fromisoformat(str(event["timestamp"])).timestamp()),
        CLASS_NAMES.index(str(event["classification"])),
        round(float(event["confidence"]) * 10_000),
        round(float(event["rms_g"]) * 10_000),
        round(float(event["peak_g"]) * 10_000),
        min(65_535, round(float(event["latency_ms"]) * 1_000)),
    )


def decode_vibration_event(payload: bytes) -> dict[str, object]:
    if len(payload) != PAYLOAD_SIZE:
        raise ValueError(f"Unexpected vibration payload size: {len(payload)}")
    event_id, timestamp, class_index, confidence, rms, peak, latency = struct.unpack(
        PAYLOAD_FORMAT, payload
    )
    return {
        "event_type": "vibration",
        "event_id": str(uuid.UUID(bytes=event_id)),
        "timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        "edge_id": VIBRATION_EDGE_ID,
        "classification": CLASS_NAMES[class_index],
        "confidence": confidence / 10_000.0,
        "rms_g": rms / 10_000.0,
        "peak_g": peak / 10_000.0,
        "latency_ms": latency / 1_000.0,
        "model": "Tiny 1D CNN",
        "model_parameters": MODEL_PARAMETERS,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_samples": WINDOW_SIZE,
        "resource_profile": VIBRATION_EDGE_PROFILE,
    }
