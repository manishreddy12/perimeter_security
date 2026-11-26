from controller import Supervisor


def main() -> None:
    supervisor = Supervisor()
    timestep = int(supervisor.getBasicTimeStep())
    if "Edge-1" in supervisor.getName():
        labels = (
            ("EDGE-1: NORTH-GATE CAMERA WORLD", 0xFFFFFF),
            ("GREEN - CAMERA EDGE (YOLO11n)", 0x43E080),
            ("BLUE  - LORAWAN GATEWAY RELAY", 0x78B8FF),
            ("BROWN - SHARED NORTH-GATE FENCE", 0xF0B080),
            ("ORANGE - EDGE-2 SENSOR LOCATION", 0xFFAD42),
            ("PRESS C TO CAPTURE", 0xFFFFFF),
        )
    else:
        labels = (
            ("EDGE-2: NORTH-GATE VIBRATION WORLD", 0xFFFFFF),
            ("ORANGE - VIBRATION EDGE (1D CNN)", 0xFFAD42),
            ("BLUE   - LORAWAN GATEWAY RELAY", 0x78B8FF),
            ("BROWN  - SHARED NORTH-GATE FENCE", 0xF0B080),
            ("GREEN  - EDGE-1 CAMERA LOCATION", 0x43E080),
            ("PRESS V TO INJECT VIBRATION", 0xFFFFFF),
        )
    for index, (text, color) in enumerate(labels):
        supervisor.setLabel(index, text, 0.55, 0.03 + index * 0.045, 0.025, color, 0.0, "Arial")
    while supervisor.step(timestep) != -1:
        pass


if __name__ == "__main__":
    main()
