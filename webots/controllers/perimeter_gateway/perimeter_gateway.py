import socket
import time

from controller import Robot


def main():
    robot = Robot()
    timestep = int(robot.getBasicTimeStep())
    receivers = (
        ("camera", robot.getDevice("uplink")),
        ("vibration", robot.getDevice("vibration_uplink")),
    )
    for _, receiver in receivers:
        receiver.enable(timestep)
    progress = {name: {"count": 0, "last": 0.0} for name, _ in receivers}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as backhaul:
        while robot.step(timestep) != -1:
            for edge_name, receiver in receivers:
                while receiver.getQueueLength():
                    frame = receiver.getBytes()
                    backhaul.sendto(frame, ("127.0.0.1", 16803))
                    current = time.monotonic()
                    state = progress[edge_name]
                    if current - state["last"] > 0.25:
                        state["count"] = 0
                    state["count"] += 1
                    state["last"] = current
                    frame_count = state["count"]
                    if edge_name == "vibration" or frame_count == 1 or frame_count % 10 == 0:
                        frame_counter = int.from_bytes(frame[6:8], "little")
                        edge_label = "edge-1" if edge_name == "camera" else "edge-2"
                        print(
                            f"[gateway][{edge_label}] forwarded={frame_count} "
                            f"devaddr={frame[1:5].hex().upper()} fcnt={frame_counter} "
                            f"frame={len(frame)}B -> UDP:16803",
                            flush=True,
                        )
                    receiver.nextPacket()


if __name__ == "__main__":
    main()
