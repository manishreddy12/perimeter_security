from controller import Supervisor


def main() -> None:
    supervisor = Supervisor()
    timestep = int(supervisor.getBasicTimeStep())
    labels = (
        ("WEBOTS OBJECTS", 0xFFFFFF),
        ("GREEN  - CAMERA EDGE (YOLO11n)", 0x43E080),
        ("ORANGE - VIBRATION EDGE (1D CNN)", 0xFFAD42),
        ("BLUE   - LORAWAN GATEWAY", 0x78B8FF),
        ("BROWN  - CAMERA TARGET", 0xF0B080),
    )
    for index, (text, color) in enumerate(labels):
        supervisor.setLabel(index, text, 0.55, 0.03 + index * 0.045, 0.025, color, 0.0, "Arial")
    while supervisor.step(timestep) != -1:
        pass


if __name__ == "__main__":
    main()
