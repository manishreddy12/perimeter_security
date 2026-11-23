import socket

from controller import Robot


def main():
    robot = Robot()
    timestep = int(robot.getBasicTimeStep())
    receivers = [robot.getDevice("uplink"), robot.getDevice("vibration_uplink")]
    for receiver in receivers:
        receiver.enable(timestep)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as backhaul:
        while robot.step(timestep) != -1:
            for receiver in receivers:
                while receiver.getQueueLength():
                    backhaul.sendto(receiver.getBytes(), ("127.0.0.1", 16803))
                    receiver.nextPacket()


if __name__ == "__main__":
    main()
