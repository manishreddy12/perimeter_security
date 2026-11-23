import os
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from gateway.radio import UplinkDecoder, UplinkEncoder
from vibration.payload import decode_vibration_event, encode_vibration_event


class UplinkTests(unittest.TestCase):
    def setUp(self):
        keys = {"PERIMETER_NWK_SKEY": "01" * 16, "PERIMETER_APP_SKEY": "02" * 16}
        with patch.dict(os.environ, keys):
            self.encoder = UplinkEncoder()
            self.decoder = UplinkDecoder()
        self.event = {"event_id": "test", "detections": ["box"] * 30}

    def test_uplink_round_trip_and_replay(self):
        frames = list(self.encoder.encode(self.event))
        self.assertGreater(len(frames), 1)
        self.assertTrue(all(len(frame) <= 64 for frame in frames))
        results = [self.decoder.decode(frame) for frame in frames]
        self.assertEqual(results, [None] * (len(frames) - 1) + [self.event])
        self.assertIsNone(self.decoder.decode(frames[-1]))

    def test_tampered_frame_and_missing_fragment(self):
        frames = list(self.encoder.encode(self.event))
        modified = frames[0][:-1] + bytes([frames[0][-1] ^ 1])
        self.assertIsNone(self.decoder.decode(modified))
        self.assertTrue(all(self.decoder.decode(frame) is None for frame in frames[1:]))
        results = [self.decoder.decode(frame) for frame in self.encoder.encode(self.event)]
        self.assertEqual(results[-1], self.event)

    def test_two_devices_use_independent_addresses_and_keys(self):
        keys = {
            "PERIMETER_VIBRATION_NWK_SKEY": "03" * 16,
            "PERIMETER_VIBRATION_APP_SKEY": "04" * 16,
        }
        with patch.dict(os.environ, keys):
            encoder = UplinkEncoder(
                "da1b0226",
                "PERIMETER_VIBRATION_NWK_SKEY",
                "PERIMETER_VIBRATION_APP_SKEY",
            )
            decoder = UplinkDecoder(
                "da1b0226",
                "PERIMETER_VIBRATION_NWK_SKEY",
                "PERIMETER_VIBRATION_APP_SKEY",
            )
        event = {"event_type": "vibration", "event_id": "sensor-test"}
        frames = list(encoder.encode(event))
        self.assertEqual(frames[0][1:5], bytes.fromhex("da1b0226"))
        self.assertEqual([decoder.decode(frame) for frame in frames][-1], event)
        self.assertIsNone(self.decoder.decode(frames[0]))

    def test_vibration_result_fits_one_lorawan_frame(self):
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "classification": "vibration_anomaly",
            "confidence": 0.9876,
            "rms_g": 0.4321,
            "peak_g": 0.8765,
            "latency_ms": 0.421,
        }
        keys = {
            "PERIMETER_VIBRATION_NWK_SKEY": "03" * 16,
            "PERIMETER_VIBRATION_APP_SKEY": "04" * 16,
        }
        with patch.dict(os.environ, keys):
            encoder = UplinkEncoder(
                "da1b0226",
                "PERIMETER_VIBRATION_NWK_SKEY",
                "PERIMETER_VIBRATION_APP_SKEY",
            )
            decoder = UplinkDecoder(
                "da1b0226",
                "PERIMETER_VIBRATION_NWK_SKEY",
                "PERIMETER_VIBRATION_APP_SKEY",
                json_payload=False,
            )
        frames = list(encoder.encode_bytes(encode_vibration_event(event)))
        self.assertEqual(len(frames), 1)
        decoded = decode_vibration_event(decoder.decode(frames[0]))
        self.assertEqual(decoded["event_id"], event["event_id"])
        self.assertEqual(decoded["classification"], "vibration_anomaly")
