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
    camera_device = bytes.fromhex(CAMERA_LORAWAN_DEVICE)
    vibration_device = bytes.fromhex(VIBRATION_LORAWAN_DEVICE)
    decoders = {
        camera_device: UplinkDecoder(CAMERA_LORAWAN_DEVICE),
        vibration_device: UplinkDecoder(
            VIBRATION_LORAWAN_DEVICE,
            "PERIMETER_VIBRATION_NWK_SKEY",
            "PERIMETER_VIBRATION_APP_SKEY",
            json_payload=False,
        ),
    }
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
    client.loop_start()
    fragment_counts = {camera_device: 0, vibration_device: 0}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as backhaul:
            backhaul.bind(("127.0.0.1", 16803))
            print("[network] gateway backhaul listening on UDP 16803", flush=True)
            while True:
                frame, _ = backhaul.recvfrom(1024)
                try:
                    device = frame[1:5]
                    decoder = decoders.get(device)
                    if decoder is not None:
                        fragment_counts[device] += 1
                    event = decoder.decode(frame) if decoder is not None else None
                    if event is not None and device == vibration_device:
                        event = decode_vibration_event(event)
                    if event is not None:
                        fragments = fragment_counts[device]
                        fragment_counts[device] = 0
                        edge_id = str(event.get("edge_id", EDGE_ID))
                        if event.get("event_type") == "vibration":
                            edge_id = VIBRATION_EDGE_ID
                            print(
                                f"[lorawan-rx][edge-2] zone={event['zone']} "
                                f"event={event['event_id'][:8]} fragments={fragments} "
                                f"anomaly={'YES' if event['classification'] == 'vibration_anomaly' else 'NO'} "
                                f"confidence={event['confidence']:.1%} rms={event['rms_g']:.4f}g",
                                flush=True,
                            )
                        else:
                            edge_result = event["edge_result"]
                            print(
                                f"[lorawan-rx][edge-1] "
                                f"zone={event['camera_event'].get('zone', 'north-gate')} "
                                f"event={event['event_id'][:8]} fragments={fragments} "
                                f"object={edge_result['summary']} boxes={len(edge_result['detections'])} "
                                f"decision={event['offload']['selected_location']}",
                                flush=True,
                            )
                        mqtt_topic = edge_topic(edge_id)
                        info = client.publish(mqtt_topic, json.dumps(event), qos=MQTT_QOS)
                        info.wait_for_publish(timeout=5)
                        if info.is_published():
                            print(
                                f"[network] event={event['event_id'][:8]} -> MQTT {mqtt_topic}",
                                flush=True,
                            )
                        else:
                            print("[network] MQTT did not acknowledge the uplink", flush=True)
                except (ValueError, RuntimeError) as exc:
                    print(f"[network] uplink failed: {exc}", flush=True)
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
