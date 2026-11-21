from __future__ import annotations

import asyncio

from amqtt.broker import Broker

from config import MQTT_HOST, MQTT_PORT


BROKER_CONFIG = {
    "listeners": {
        "default": {
            "type": "tcp",
            "bind": f"{MQTT_HOST}:{MQTT_PORT}",
        }
    },
    "plugins": {
        "amqtt.plugins.authentication.AnonymousAuthPlugin": {
            "allow_anonymous": True
        },
        "amqtt.plugins.sys.broker.BrokerSysPlugin": {"sys_interval": 10},
    },
}


async def run_broker() -> None:
    broker = Broker(BROKER_CONFIG)
    await broker.start()
    print(f"[broker] MQTT 3.1.1 listening on {MQTT_HOST}:{MQTT_PORT}", flush=True)
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await broker.shutdown()


def main() -> None:
    try:
        asyncio.run(run_broker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
