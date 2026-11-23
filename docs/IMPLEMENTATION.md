# Perimeter Security Implementation Document

## 1. Purpose and scope

This document describes the implementation of the current RGB and vibration perimeter-security demonstration in this repository. It covers the code that runs today, the communication paths, the models, storage, APIs, startup process, and known limitations.

The application is a functional local demonstration. All neural-network inference currently executes on the Windows laptop CPU. Webots supplies a simulated world and simulated radio devices; it does not emulate Jetson CPU/GPU performance, LoRa RF propagation, energy consumption, or physical sensor accuracy.

The older synthetic 5×4 sensor-matrix application is a separate demonstration and is not described here.

## 2. Implemented system overview

The application contains two logical edge devices:

1. A camera edge with a simulated NVIDIA Jetson Nano resource profile and YOLO11n.
2. A fixed low-power vibration edge with a 512 MB, 2 W profile and a tiny 1D CNN.

The laptop also runs the application infrastructure:

- an embedded MQTT broker;
- the Flask API and dashboard;
- a conditional YOLO11m cloud model;
- an SQLite database;
- and, in Webots mode, a simulated LoRaWAN network server.

```text
Camera input
  -> YOLO11n edge inference
  -> edge/cloud decision
  -> simulated LoRaWAN in Webots mode
  -> gateway -> UDP network server -> MQTT
  -> optional YOLO11m cloud inference
  -> OpenCV annotation -> SQLite -> dashboard

Synthetic vibration window
  -> tiny 1D CNN edge inference
  -> compact simulated LoRaWAN uplink
  -> gateway -> UDP network server -> MQTT
  -> SQLite -> dashboard/alert
```

## 3. Execution modes

### 3.1 Default MQTT mode

Command:

```powershell
.\myenv\Scripts\python.exe run_demo.py
```

`run_demo.py` starts these Python processes:

1. `broker.app` — embedded MQTT broker.
2. `cloud.app` — Flask application, YOLO11m, database, and MQTT consumer.
3. `edge.app` — logical YOLO11n edge worker.

Camera events and edge results both travel through MQTT. Webots, the vibration edge, simulated LoRaWAN, and the UDP network server are not started.

### 3.2 Webots mode

Command:

```powershell
.\myenv\Scripts\python.exe run_demo.py --webots
```

The launcher starts:

1. `broker.app`;
2. `cloud.app`;
3. `gateway.network_server`;
4. Webots with `webots/worlds/perimeter.wbt`.

Webots then starts four controllers:

| Controller | Responsibility |
| --- | --- |
| `scene_labels` | Draws the fixed color legend in the 3D view. |
| `perimeter_edge` | Captures the camera, runs YOLO11n, and sends camera results by simulated LoRaWAN. |
| `vibration_edge` | Generates synthetic vibration windows, runs the 1D CNN, and sends compact results by simulated LoRaWAN. |
| `perimeter_gateway` | Receives Webots radio packets and relays them to UDP port 16803. |

The launcher generates fresh camera and vibration ABP session keys for every run and passes them to the network server and Webots controllers through environment variables.

## 4. Process and port map

| Component | Implementation | Address/port |
| --- | --- | --- |
| MQTT broker | Python `amqtt` broker | `127.0.0.1:1883` |
| MQTT clients | Python `paho-mqtt` | Connect to port 1883 |
| Flask dashboard/API | Flask development server | `127.0.0.1:8000` |
| Gateway backhaul | UDP socket | `127.0.0.1:16803` |
| Database | SQLite | `perimeter_events.db` |

MQTT does not use Docker, Mosquitto, or an external cloud service. `broker/app.py` creates an MQTT 3.1.1 broker from the `amqtt` library. Anonymous connections are enabled for this localhost demonstration.

The following environment variables override default network settings:

- `PERIMETER_MQTT_HOST`
- `PERIMETER_MQTT_PORT`
- `PERIMETER_CLOUD_HOST`
- `PERIMETER_CLOUD_PORT`
- `PERIMETER_WEBOTS_EXE`

Ultralytics settings are stored under `.runtime/ultralytics` so the launcher does not depend on write access to the Windows roaming-profile directory.

## 5. Camera inference implementation

### 5.1 Input sources

The application accepts camera events from three sources:

- one of nine built-in sample images through `POST /api/run`;
- a user image through `POST /api/upload`;
- the Webots camera through `POST /api/webots/capture`.

Uploads accept JPG, PNG, and WebP. The application reads at most 8 MB, decodes the image with OpenCV, limits the longest side to 1600 pixels, converts it to JPEG, and keeps at most 20 uploaded images in memory.

MQTT carries image metadata and an HTTP URL, not raw JPEG bytes. Webots posts a captured JPEG to Flask so it can receive a temporary URL, but YOLO11n performs inference locally on the already captured frame.

### 5.2 YOLO11n edge stage

`edge/app.py` loads `yolo11n.pt` through the Ultralytics `YOLO` class and runs:

- input size: 416 pixels;
- confidence threshold: 0.25;
- device: CPU.

Only configured security classes are retained:

- person;
- car, motorcycle, bus, and truck;
- common COCO animal classes.

Each retained detection contains its class, confidence, and `[x1, y1, x2, y2]` bounding box. The summary priority is vehicle, person, animal, then normal.

### 5.3 Offloading rule

The current decision is a hand-written rule:

| Edge result | Decision |
| --- | --- |
| Person | Run YOLO11m in the cloud service. |
| Vehicle | Run YOLO11m in the cloud service. |
| Any retained detection below 0.50 maximum confidence | Run YOLO11m in the cloud service. |
| Confident animal | Accept YOLO11n. |
| No configured security detection | Accept YOLO11n. |

This is not an ML scheduler, SCI calculation, or carbon-aware offloading policy.

### 5.4 YOLO11m cloud stage

`cloud/app.py` loads `yolo11m.pt` at startup. It runs only when the edge selects `cloud`:

- input size: 640 pixels;
- confidence threshold: 0.25;
- device: CPU.

If the edge selects `edge`, YOLO11m is skipped and the YOLO11n detections become the final detections. OpenCV draws the selected model's bounding boxes and labels and stores the annotated JPEG as Base64 in SQLite.

A final person or vehicle summary creates an alert. An animal result is not currently an alert.

## 6. Vibration inference implementation

The orange vibration box is fixed in the Webots world. It has no physical dynamics, so gravity and collision forces cannot move it. The controller generates reproducible synthetic samples using random seed 2026.

The input configuration is:

- 64 samples per window;
- 31.25 Hz sample rate;
- approximately 2.05 seconds per window;
- normal baseline noise with standard deviation 0.01;
- an injected 8 Hz sinusoid with amplitude 0.55 for demonstration anomalies.

Pressing `V` in the focused Webots view injects an anomaly into the next/current window. Every fourth window also receives an automatic demonstration anomaly.

The `TinyVibrationCNN` architecture is:

```text
1 input channel
  -> Conv1d(1, 8, kernel 5) -> ReLU -> MaxPool1d(2)
  -> Conv1d(8, 16, kernel 3) -> ReLU
  -> AdaptiveAvgPool1d(1)
  -> Linear(16, 2)
  -> normal or vibration_anomaly
```

The model has 482 parameters and loads `vibration/tiny_vibration_cnn.pt`. It was trained on synthetic signals, so its result demonstrates the pipeline and must not be presented as field accuracy.

## 7. Simulated LoRaWAN and gateway

### 7.1 Radio path

In Webots mode, camera and vibration inference results follow this path:

```text
Edge controller
  -> Webots Emitter
  -> Webots Receiver in the blue gateway
  -> UDP 127.0.0.1:16803
  -> gateway/network_server.py
  -> MQTT perimeter/edge/<edge-id>/result
```

The camera radio uses Webots channel 40. The vibration radio uses channel 41.

### 7.2 Frame implementation

`gateway/radio.py` implements a local LoRaWAN 1.0-style unconfirmed ABP uplink:

- separate device addresses and session keys for both edge devices;
- AES payload encryption;
- AES-CMAC message integrity code;
- uplink frame counters;
- replay and large-counter-gap rejection;
- application-specific fragmentation and reassembly;
- maximum Webots radio frame length of 64 bytes;
- 43 application bytes per fragment.

Camera results are JSON and may require multiple fragments. Vibration results are encoded into a 29-byte binary application payload and fit within one uplink frame.

This implementation demonstrates encrypted frame handling and gateway/application integration. It does not simulate RF propagation, spreading factors, frequencies, airtime, duty cycle, adaptive data rate, join procedures, downlinks, or a physical LoRaWAN gateway.

RGB images never travel over the simulated LoRaWAN path. Only compact inference results and metadata use it. The temporary image remains available through local HTTP for annotation and optional YOLO11m verification.

## 8. MQTT implementation

All MQTT messages use QoS 1.

| Topic | Producer | Consumer | Purpose |
| --- | --- | --- | --- |
| `perimeter/camera/+/image` | Flask API or mock camera | YOLO11n edge service | Camera event metadata and image URL. |
| `perimeter/edge/+/result` | Edge service or LoRa network server | Cloud service | Camera or vibration inference result. |
| `perimeter/status/+/state` | Edge and cloud components | Cloud service/dashboard | Retained online/offline state and resource metadata. |
| `perimeter/alerts` | Cloud service | Optional subscribers | Final camera or vibration alerts. |
| `perimeter/cloud/<edge-id>/result` | Cloud service | Optional subscribers | Compact camera completion result. |

In Webots mode, edge controllers still use MQTT for retained component status. Camera and vibration inference results use the simulated radio/gateway path before entering MQTT.

## 9. Flask API

| Method and route | Purpose |
| --- | --- |
| `GET /` | Dashboard page. |
| `GET /api/health` | Cloud/MQTT readiness. |
| `GET /api/status` | Broker, camera edge, vibration edge, and cloud state. |
| `GET /api/images` | Built-in sample list. |
| `GET /api/events` | Recent camera events. |
| `GET /api/vibration-events` | Recent vibration events. |
| `POST /api/run` | Queue a built-in sample through MQTT. |
| `POST /api/upload` | Validate/store an uploaded image and queue it through MQTT. |
| `POST /api/webots/capture` | Store a Webots camera frame and return its event metadata. |
| `GET /uploads/<id>` | Serve an in-memory temporary JPEG. |
| `POST /api/reset` | Clear both event tables and in-memory uploads. |

The browser polls status every 3 seconds and event data every 2 seconds. These reads do not trigger inference.

## 10. Persistence

SQLite stores two tables.

The `events` table stores camera event identity, source and URL, edge and final summaries, detections, execution location, decision reason, edge/cloud latency, alert state, Webots sensor metadata, and the annotated image.

The `vibration_events` table stores event identity, edge ID, classification, confidence, RMS and peak values, inference latency, model details, sample configuration, resource profile, and alert state.

Built-in sample records can persist across restarts. Browser and Webots images are stored only in memory, and upload-sourced camera records are deleted during application initialization because their URLs are no longer valid after restart.

`perimeter_events.db` is generated runtime state, not source data or a labelled evaluation dataset.

## 11. Startup, readiness, and shutdown

`run_demo.py` performs these checks:

1. Confirms required model files exist.
2. Starts the broker and waits for an MQTT connection.
3. Starts Flask and waits for `/api/health`.
4. Starts the logical edge, or the Webots network server and Webots.
5. Polls `/api/status` until the required edge services report online.
6. Prints the ready message and monitors child processes.

Press `Ctrl+C` once in the launching PowerShell window to stop the complete process tree. The launcher ignores additional interrupt signals during cleanup and uses Windows process-tree termination for child services.

Before restarting after an abnormal termination, confirm that ports 1883, 8000, and UDP 16803 are not owned by stale processes.

## 12. Validation

Run from the repository root:

```powershell
.\myenv\Scripts\python.exe -B -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m pip check
node --check cloud\static\app.js
```

The Python suite covers model assets, samples, topics, security summaries, offloading, answer-free input events, the vibration model/profile, independent LoRaWAN device keys, compact vibration payloads, fragmentation, integrity checking, and replay rejection.

For an end-to-end Webots check, wait for the launcher ready message and confirm terminal entries from `[edge]`, `[vibration-edge]`, `[network]`, and `[cloud]`.

## 13. Main source files

| File | Implementation responsibility |
| --- | --- |
| `run_demo.py` | Process launcher, model checks, readiness, keys, and cleanup. |
| `config.py` | Ports, topics, model paths, IDs, classes, samples, and resource profiles. |
| `broker/app.py` | Embedded `amqtt` broker. |
| `edge/app.py` | YOLO11n inference, summaries, offloading, and logical-edge MQTT service. |
| `cloud/app.py` | Flask, YOLO11m, annotation, MQTT consumption, alerts, and SQLite. |
| `gateway/radio.py` | Simulated LoRaWAN framing, encryption, MIC, counters, and reassembly. |
| `gateway/network_server.py` | UDP gateway backhaul decoding and MQTT publication. |
| `vibration/model.py` | 482-parameter 1D CNN. |
| `vibration/payload.py` | Compact 29-byte vibration payload. |
| `vibration/train_model.py` | Reproducible synthetic model training. |
| `webots/worlds/perimeter.wbt` | Scene, devices, radio channels, and controller assignments. |
| `webots/controllers/perimeter_edge/` | Webots camera capture and YOLO11n result uplink. |
| `webots/controllers/vibration_edge/` | Synthetic vibration window generation and CNN uplink. |
| `webots/controllers/perimeter_gateway/` | Radio-to-UDP forwarding. |
| `cloud/static/app.js` | Dashboard requests, polling, and rendering. |

## 14. Current limitations and future physical deployment

The implementation does not currently provide:

- physical Jetson execution, CUDA, TensorRT, or ARM emulation;
- real camera or vibration hardware;
- physical LoRa radios or measured network behaviour;
- field-labelled accuracy evaluation;
- measured power, energy, temperature, or SCI values;
- learned, SLA-aware, or carbon-aware offloading;
- MQTT authentication, TLS, user accounts, or production security;
- production Flask hosting or durable uploaded-image storage.

A physical deployment should run an exported TensorRT YOLO11n model on a Jetson, acquire synchronized real sensor data, use a real LoRaWAN end device/gateway/network server for compact results, transfer selected images over an IP-capable link, and measure latency and energy on the target hardware.
