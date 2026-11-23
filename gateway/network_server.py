"""Receive gateway backhaul and publish reconstructed application events."""

import json
import socket

import paho.mqtt.client as mqtt

from config import (
    CAMERA_LORAWAN_DEVICE,
    EDGE_ID,
    MQTT_HOST,
    MQTT_KEEPALIVE,
    MQTT_PORT,
    MQTT_QOS,
    VIBRATION_EDGE_ID,
    VIBRATION_LORAWAN_DEVICE,
    edge_topic,
)
from gateway.radio import UplinkDecoder
from vibration.payload import decode_vibration_event


def main():
    decoders = {
        bytes.fromhex(CAMERA_LORAWAN_DEVICE): UplinkDecoder(CAMERA_LORAWAN_DEVICE),
        bytes.fromhex(VIBRATION_LORAWAN_DEVICE): UplinkDecoder(
            VIBRATION_LORAWAN_DEVICE,
            "PERIMETER_VIBRATION_NWK_SKEY",
            "PERIMETER_VIBRATION_APP_SKEY",
            json_payload=False,
        ),
    }
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
    client.loop_start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as backhaul:
            backhaul.bind(("127.0.0.1", 16803))
            print("[network] gateway backhaul listening on UDP 16803", flush=True)
            while True:
                frame, _ = backhaul.recvfrom(1024)
                try:
                    decoder = decoders.get(frame[1:5])
                    event = decoder.decode(frame) if decoder is not None else None
                    if event is not None and decoder is decoders[bytes.fromhex(VIBRATION_LORAWAN_DEVICE)]:
                        event = decode_vibration_event(event)
                    if event is not None:
                        edge_id = str(event.get("edge_id", EDGE_ID))
                        if event.get("event_type") == "vibration":
                            edge_id = VIBRATION_EDGE_ID
                        info = client.publish(edge_topic(edge_id), json.dumps(event), qos=MQTT_QOS)
                        info.wait_for_publish(timeout=5)
                        if info.is_published():
                            print(f"[network] uplink {event['event_id']} published over MQTT", flush=True)
                        else:
                            print("[network] MQTT did not acknowledge the uplink", flush=True)
                except (ValueError, RuntimeError) as exc:
                    print(f"[network] uplink failed: {exc}", flush=True)
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
