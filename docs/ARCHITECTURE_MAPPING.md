# Mapping the demonstration to the proposed architecture

## Purpose

This document maps the working Webots demonstration to the blocks in the proposed perimeter-security architecture. Use it when explaining which parts are executable software, which parts are simulated, and which parts remain future physical deployment work.

## One-sentence project description

Webots supplies mock camera and vibration inputs plus logical edge and gateway nodes; real ML code performs edge inference; compact results cross a simulated LoRaWAN-style uplink; a network server publishes the reconstructed events through MQTT; and the application server performs logging, alerts, dashboard updates, and conditional YOLO11m verification.

## Block-by-block mapping

| Proposed architecture block | Current project component | Implementation status |
| --- | --- | --- |
| Physical sensors | Webots RGB camera and synthetic vibration generator | Mock input |
| Edge-1 device | Edge-1 Webots world and `camera_edge` controller | Jetson Nano profile + YOLO11n |
| Edge-2 device | Edge-2 Webots world and `vibration_edge` controller | Simple device profile + 1D CNN |
| Edge inference | YOLO11n and `TinyVibrationCNN` | Real model execution on laptop CPU |
| LoRaWAN end device | `gateway/radio.py` encoder used by each edge controller | Software frame simulation |
| LoRaWAN gateway | Webots `perimeter_gateway` controller | Simulated gateway relay |
| Gateway backhaul | UDP `127.0.0.1:16803` | Real localhost UDP transport |
| Network server | `gateway/network_server.py` | Real frame verification, decoding and reassembly |
| MQTT broker | Embedded `amqtt` broker on `127.0.0.1:1883` | Real local messaging |
| Application server | Flask and MQTT consumer in `cloud/app.py` | Real local service |
| Cloud inference | Conditional YOLO11m | Real model execution on laptop CPU |
| Database | SQLite `perimeter_events.db` | Real local persistence |
| Dashboard | Flask HTML/CSS/JavaScript | Real local UI |
| Runtime monitor | Retained MQTT component state and `GET /api/status` | Basic status only |

## Camera path

```text
Webots Edge-1 mock camera
  -> camera_edge controller
  -> YOLO11n edge inference
  -> edge/cloud decision
  -> encrypted LoRaWAN-style result frames on channel 40
  -> Webots gateway
  -> UDP 16803
  -> network server verifies MIC/counter and reassembles JSON
  -> MQTT perimeter/edge/simulated-edge-01/result
  -> application server
       -> accept YOLO11n result, or
       -> run YOLO11m for cloud verification
  -> annotation, SQLite, alert and dashboard
```

The JPEG follows a separate local HTTP path. It is never placed in the simulated LoRaWAN frames. See [IMAGE_TRANSFER_FLOW.md](IMAGE_TRANSFER_FLOW.md).

## Vibration path

```text
Webots Edge-2 synthetic vibration samples
  -> 64-sample edge window
  -> TinyVibrationCNN
  -> 29-byte binary application result
  -> encrypted LoRaWAN-style uplink on channel 41
  -> Webots gateway
  -> UDP 16803
  -> network server verifies and decodes payload
  -> MQTT perimeter/edge/vibration-edge-01/result
  -> application server
  -> SQLite, alert topic and dashboard
```

## How both worlds represent the same monitored area

Both world files use a shared digital-twin layout:

```text
zone: north-gate
Edge-1 camera position:      (0, 0, 1)
North Gate fence position:   (3, 0, 1)
Edge-2 sensor position:      (2.82, -0.75, 0.8)
gateway display position:    (0, -2, 0)
```

The Edge-1 camera faces the brown North Gate fence. Its view also shows an orange marker at the vibration-sensor location. The Edge-2 world contains the actual orange logical vibration node at that same location and a green marker for the camera position. Thus both devices are presented as monitoring one fence section.

This is spatial correspondence, not cross-world physics synchronization. A person or impact created in one Webots instance is not automatically copied into the other, and camera/vibration events are not yet joined into a common incident.

## Recommended changes to the architecture diagram

### Rename the sensor block

Replace `Physical Sensors` with:

```text
Webots Mock Sensors
- RGB camera
- Synthetic vibration
```

For a future-deployment diagram, keep `Physical Sensors` but mark the Webots block as the demonstration substitute.

### Split or expand the edge block

The implementation contains two logical edge devices in separate Webots worlds:

```text
Edge-1 world
- Jetson Nano profile
- RGB camera
- YOLO11n -> object class and bounding boxes

Edge-2 world
- Simple-device profile
- Synthetic vibration windows
- Tiny 1D CNN -> normal/anomaly decision
```

They monitor the same named area but remain separate controllers, device identities, radio channels and payloads. Do not draw them as one fused sensor unless the code is later changed.

### Rename the inference stages

The labels `Inference-I` and `Inference-II` are ambiguous because edge inference happens first. Prefer:

- `Stage 1: Edge inference` for YOLO11n and the vibration CNN.
- `Stage 2: Cloud verification` for conditional YOLO11m.

### Label the gateway and network server separately

Use:

```text
Webots simulated LoRaWAN gateway
  -> UDP backhaul
Local network server
  -> LoRaWAN-style decode
  -> MQTT publication
```

Each world displays a gateway relay because Webots radio does not cross between independent world processes. Both relay controllers forward to the same UDP port and therefore represent the single logical gateway/network-server path in the architecture. The gateway does not publish MQTT directly; the Python network server publishes the decoded application event.

### Add the image path

Draw a second line for camera images:

```text
Camera/Web UI -> local HTTP image store -> edge/cloud image retrieval
```

Label the LoRaWAN path `compact detections and metadata only`.

### Qualify the runtime monitor

The current runtime-monitor block should say:

```text
Basic runtime status
- retained MQTT state
- /api/status
- processed-event count
```

The project does not yet implement a general metrics, resource, energy or SLA monitoring platform.

## What is real, simulated and future work

| Category | Examples |
| --- | --- |
| Executable software | YOLO11n, YOLO11m, vibration CNN, AES encryption, MIC, counters, fragmentation, UDP, MQTT, Flask, SQLite, dashboard |
| Simulated/mock | Camera scene, vibration samples, device resource profiles, Webots radio transport, gateway object |
| Future physical deployment | Jetson/TensorRT execution, real camera and accelerometer, physical LoRaWAN radio/gateway, measured power, SCI and field evaluation |

## Presentation wording

Suggested explanation:

> Webots is the functional mock environment for the sensor and edge tier. Its camera and vibration controllers execute the edge models and create compact results. Those results are encoded as encrypted LoRaWAN-style uplinks and relayed through the Webots gateway to the local network server. The network server verifies and reconstructs each result and publishes it over MQTT. The application server stores the event, updates the dashboard, generates alerts and runs YOLO11m only when the camera edge requests verification.

Follow it with this boundary statement:

> The sensor values and hardware profiles are simulated. The inference code, frame security logic, UDP transport, MQTT delivery, database operations and dashboard processing are executable software components.

## Claims to avoid

Do not say that the demonstration provides:

- physical Jetson execution or Jetson performance;
- real accelerometer measurements;
- LoRa RF propagation, range, airtime or duty-cycle results;
- real energy, power or SCI measurement;
- field accuracy for either vision or vibration models.

Use `logical edge`, `mock sensor`, `simulated LoRaWAN-style uplink`, and `local application server` when presenting the current version.
