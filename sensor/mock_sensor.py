from __future__ import annotations

import argparse
import itertools
import json
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from config import (
    CLOUD_URL,
    DEMO_IMAGES,
    MQTT_HOST,
    MQTT_KEEPALIVE,
    MQTT_PORT,
    MQTT_QOS,
    sensor_topic,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish RGB camera events through MQTT")
    parser.add_argument("--image", choices=[*DEMO_IMAGES, "cycle"], default="cycle")
    parser.add_argument("--count", type=int, default=0, help="0 runs until Ctrl+C")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--camera-id", default="rgb-camera-01")
    parser.add_argument("--zone", default="north-gate")
    parser.add_argument("--broker-host", default=MQTT_HOST)
    parser.add_argument("--broker-port", type=int, default=MQTT_PORT)
    args = parser.parse_args()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"mock-camera-{args.camera_id}",
        protocol=mqtt.MQTTv311,
    )
    client.connect(args.broker_host, args.broker_port, MQTT_KEEPALIVE)
    client.loop_start()
    sequence = itertools.cycle(DEMO_IMAGES)
    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            image_key = next(sequence) if args.image == "cycle" else args.image
            image_file = DEMO_IMAGES[image_key]["file"]
            event = {
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "camera_id": args.camera_id,
                "zone": args.zone,
                "image_name": DEMO_IMAGES[image_key]["title"],
                "image_url": f"{CLOUD_URL}/static/{image_file}",
                "source": "sample",
            }
            info = client.publish(sensor_topic(args.camera_id), json.dumps(event), qos=MQTT_QOS)
            info.wait_for_publish(timeout=5)
            print(f"[camera] published {image_key} image event", flush=True)
            sent += 1
            if args.count == 0 or sent < args.count:
                time.sleep(max(0.5, args.interval))
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
