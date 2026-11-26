# Agent guide: final Perimeter Security project

This repository is the final, self-contained version of the college project. Read this file before changing code, then read `README.md`, `docs/README.md`, and `docs/IMPLEMENTATION.md`.

## Scope

The application demonstrates local edge/cloud ML orchestration for perimeter-security events. It has two execution modes:

1. The default MQTT-only mode runs a logical RGB edge worker, cloud service, and embedded MQTT broker as separate Python processes.
2. Optional Webots mode runs a simulated camera edge, a separate vibration edge, a simulated radio gateway, and the same laptop cloud service.

Everything in this repository belongs to this final application. Older prototypes in sibling workspace folders are not part of this checkout. Do not copy their models, ports, databases, datasets, or accuracy claims into this project.

The code is a functional execution-flow demonstration, not a physical-hardware or performance simulation. Neural-network inference runs on the Windows laptop CPU in both modes. Webots supplies a 3D scene and logical devices; it does not emulate Jetson compute performance, physical vibration, LoRa RF behavior, energy use, or field accuracy.

## Start commands

From PowerShell:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security-main
.\myenv\Scripts\python.exe run_demo.py
```

Open http://127.0.0.1:8000 after the terminal prints `RGB object-detection demo is running`.

`myenv/` is generated and is not portable between computers or Python installations. If its launcher reports `No Python at ...`, move the stale environment aside and recreate it with Python 3.13 using the setup commands in `docs/README.md`; do not edit `pyvenv.cfg` to point at an unrelated interpreter.

For the full Webots demonstration:

```powershell
.\myenv\Scripts\python.exe run_demo.py --webots
```

The world targets Webots R2025a. If Webots is not found automatically, set `PERIMETER_WEBOTS_EXE` to `webots.exe`. Click the PowerShell window and press `Ctrl+C` once to stop the complete process tree.

Default ports are:

- MQTT broker: TCP `127.0.0.1:1883`
- Flask dashboard/API: TCP `127.0.0.1:8000`
- Webots gateway backhaul: UDP `127.0.0.1:16803`

The following environment variables override network or simulator settings:

- `PERIMETER_MQTT_HOST`
- `PERIMETER_MQTT_PORT`
- `PERIMETER_CLOUD_HOST`
- `PERIMETER_CLOUD_PORT`
- `PERIMETER_WEBOTS_EXE`

`run_demo.py` creates `.runtime/ultralytics` and sets `YOLO_CONFIG_DIR` there so Ultralytics does not require a writable roaming-profile directory.

## What the launcher starts

### Default MQTT-only mode

`run_demo.py` starts these modules in order:

1. `broker.app`
2. `cloud.app`
3. `edge.app`

It waits for the MQTT broker, `GET /api/health`, and the retained RGB edge status before printing the ready message. Webots, the vibration edge, the network server, and UDP port 16803 are not used.

The default dashboard still renders the vibration panel. Because `cloud/static/app.js` currently requires both edge devices to be online for its combined status banner, the banner can say `WAITING FOR EDGE DEVICES` in MQTT-only mode even when the terminal is ready and RGB inference works. Treat `/api/status` and the launcher message as the source of truth.

### Webots mode

`run_demo.py --webots` starts:

1. `broker.app`
2. `cloud.app`
3. `gateway.network_server`
4. Webots with `webots/worlds/edge1_camera_jetson.wbt`
5. Webots with `webots/worlds/edge2_vibration_device.wbt`

The two worlds keep the edge devices visually and functionally separate:

- Edge-1 world: `camera_edge`, `perimeter_gateway`, and `scene_labels`
- Edge-2 world: `vibration_edge`, `perimeter_gateway`, and `scene_labels`

Both worlds use the same `north-gate` fence at the same coordinates and show a reference marker for the other edge device. This represents two views of one monitored area. The Webots processes do not share physics state, event timing, or an incident/correlation model.

Each world shows a gateway relay, while both relays feed the same logical UDP network-server path. The launcher creates fresh, independent camera and vibration ABP session keys for every Webots run. Resetting either world can desynchronize frame counters; restart the launcher to establish fresh keys and counters.

## Implemented flows

### Default RGB flow

```text
Browser sample/upload or mock camera
  -> camera metadata plus image_url over MQTT
  -> edge/app.py downloads the JPEG
  -> YOLO11n at 416 px on laptop CPU
  -> rule chooses edge acceptance or cloud verification
  -> edge result over MQTT
  -> cloud/app.py accepts YOLO11n or runs YOLO11m at 640 px
  -> OpenCV annotation
  -> SQLite and dashboard
```

`POST /api/run` and `POST /api/upload` return HTTP 202 after queuing work. They do not wait for inference. The browser learns about completed results by polling `GET /api/events`.

### Webots camera flow

```text
Initial capture or C key
  -> Webots camera frame
  -> POST /api/webots/capture stores a temporary JPEG and returns metadata
  -> YOLO11n runs in the Webots controller process on laptop CPU
  -> encrypted, fragmented simulated LoRaWAN uplink on channel 40
  -> Webots gateway -> UDP 16803 -> network server
  -> MQTT edge-result topic
  -> optional YOLO11m, annotation, SQLite, dashboard
```

The Edge-1 camera controller takes one initial capture after its MQTT connection is ready. Press `C` in the focused Edge-1 view for another capture. Browser samples and uploads still enter by MQTT in Webots mode; the Webots edge worker processes them and sends their results through the simulated radio path.

### Webots vibration flow

```text
Reproducible synthetic one-axis samples
  -> 64-sample non-overlapping window
  -> 482-parameter TinyVibrationCNN on laptop CPU
  -> 29-byte application payload
  -> encrypted simulated LoRaWAN uplink on channel 41
  -> Webots gateway -> UDP 16803 -> network server
  -> MQTT edge-result topic
  -> SQLite, alert topic, dashboard
```

The vibration node is fixed and has no physics-driven sensor. Every fourth window receives an automatic demonstration disturbance. Pressing `V` injects a disturbance into the current/next window. The controller uses seed 2026.

## Camera inputs

### Built-in samples

- Nine offline images are configured as neutral `Sample 01` through `Sample 09`.
- The browser sends only the selected key, such as `sample_03`, to `POST /api/run`.
- The cloud API builds the camera event and publishes it to MQTT.
- No preset answer, expected class, or content-revealing tag is sent with the event.

### Browser uploads

- The intended UI formats are JPG, PNG, and WebP.
- The server accepts at most 8 MB of image bytes and verifies that OpenCV can decode them.
- Images larger than 1600 pixels on their longest side are resized and converted to JPEG.
- At most 20 converted uploads are held in an in-memory ordered store.
- MQTT carries the temporary HTTP URL, never raw RGB bytes.
- Upload bytes and upload-sourced event records are not durable across restarts.

### Command-line mock camera

With the default demo already running:

```powershell
.\myenv\Scripts\python.exe -m sensor.mock_sensor --image sample_03 --count 1
```

The publisher bypasses the Flask input routes and publishes camera metadata directly to MQTT. `--image cycle` and `--count 0` continue until interrupted.

## Camera models and decision rule

### Edge stage

`edge/app.py` loads local `yolo11n.pt` with the Ultralytics `YOLO` class and uses:

- `imgsz=416`
- `conf=0.25`
- `device="cpu"`

It retains only configured COCO people, vehicles, and common animals. Each detection includes class, confidence, and `[x1, y1, x2, y2]`. Summary priority is `vehicle`, `person`, `animal`, then `normal`.

`choose_location()` implements this hand-written rule:

- `person` -> cloud
- `vehicle` -> cloud
- any retained detections whose maximum confidence is below `0.50` -> cloud
- confident animal -> edge
- no configured security detection -> edge

This is not a learned scheduler, SLA optimizer, SCI calculation, or carbon-aware offloading algorithm.

### Cloud stage

`cloud/app.py` always owns APIs, MQTT consumption, result annotation, persistence, and dashboard reads. Its local `yolo11m.pt` model runs only when the edge selected `cloud`:

- `imgsz=640`
- `conf=0.25`
- `device="cpu"`

When the edge result is accepted, YOLO11m is skipped. OpenCV draws the selected model's boxes. A final `person` or `vehicle` summary is an alert; `animal` is not.

The local checkpoint sizes are approximately 5.6 MB for YOLO11n and 40.7 MB for YOLO11m. These are different pretrained COCO model scales loaded by the same Ultralytics API. COCO performance must not be presented as accuracy at the intended perimeter site, and the nine samples/uploads have no ground-truth evaluation labels.

## Vibration model

`vibration/model.py` defines:

```text
Conv1d(1, 8, kernel 5) -> ReLU -> MaxPool1d(2)
  -> Conv1d(8, 16, kernel 3) -> ReLU
  -> AdaptiveAvgPool1d(1) -> Linear(16, 2)
```

Facts to preserve:

- input: 64 samples at 31.25 Hz, about 2.05 seconds
- output: `normal` or `vibration_anomaly`
- size: 482 trainable parameters
- checkpoint: `vibration/tiny_vibration_cnn.pt`
- metadata: `vibration/tiny_vibration_cnn.json`
- training source: reproducibly generated synthetic waveforms
- recorded training accuracy is measured on the generated training data, not an independent test set

The model demonstrates compact inference and transport. It has no field-accuracy claim.

## Simulated LoRaWAN and gateway

`gateway/radio.py` implements a local LoRaWAN 1.0-style unconfirmed ABP uplink, not a complete LoRaWAN stack. It provides:

- separate device addresses and session keys for camera and vibration nodes
- AES application-payload encryption
- AES-CMAC message integrity code
- frame counters with replay and large-gap rejection
- application-specific fragmentation and ordered reassembly
- maximum Webots radio frame length of 64 bytes
- 43 application bytes per fragment

Camera results are compact JSON and may span multiple frames. Vibration uses a 29-byte binary application payload and fits in one frame. RGB JPEGs never travel over this radio path; they remain on the local HTTP path for annotation and possible cloud verification.

Webots controllers print readable application summaries at transmission, compact progress at the gateway, and decoded summaries at the network server. Do not replace these with full decrypted camera JSON or print session keys. The vibration payload may print its 29-byte hexadecimal form because it contains only the compact result fields.

The implementation does not simulate join procedures, downlinks, radio frequencies, spreading factors, RF propagation, airtime, duty cycle, adaptive data rate, or a physical gateway. Do not call the MQTT broker a LoRaWAN gateway.

## MQTT topics

All application MQTT messages use QoS 1. The embedded `amqtt` broker permits anonymous localhost connections and has no TLS.

| Topic | Purpose |
| --- | --- |
| `perimeter/camera/+/image` | Camera metadata and HTTP image URL input |
| `perimeter/edge/+/result` | Camera or vibration edge results |
| `perimeter/status/+/state` | Retained component status and resource metadata |
| `perimeter/alerts` | Final camera and vibration alerts |
| `perimeter/cloud/<edge-id>/result` | Compact camera completion event |

In Webots mode, controller status still goes directly over MQTT. Camera and vibration inference results first traverse simulated radio, gateway, and UDP network server before entering MQTT.

## HTTP API and polling

Routes implemented by `cloud/app.py`:

- `GET /`: dashboard
- `GET /api/health`: cloud/MQTT readiness
- `GET /api/status`: broker, RGB edge, vibration edge, and cloud state
- `GET /api/images`: built-in sample metadata
- `GET /api/events`: recent RGB events
- `GET /api/vibration-events`: recent vibration events
- `POST /api/run`: queue a built-in sample
- `POST /api/upload`: store and queue a browser image
- `POST /api/webots/capture`: store a Webots frame and return metadata without MQTT publication
- `GET /uploads/<id>`: serve a temporary JPEG
- `POST /api/reset`: delete both event tables' rows and clear in-memory uploads

The browser polls status every 3 seconds and both event endpoints every 2 seconds. Polling only reads state; it does not run inference or publish camera events. `POST /api/reset` has no authentication or confirmation because this is a local demonstration.

## Persistence

Generated `perimeter_events.db` contains:

- `events`: image identity/source, edge and final summaries/detections, selected location, reason, latencies, alert, sensor metadata, and annotated Base64 JPEG
- `vibration_events`: class, confidence, RMS, peak, latency, model/window details, resource profile, and alert

Built-in sample records can survive restarts. In-memory browser/Webots images do not, so records with `image_source='upload'` are removed during cloud initialization. The database is runtime state, not a labelled dataset.

## Main file map

- `run_demo.py`: mode selection, prerequisites, startup readiness, per-run keys, monitoring, and cleanup
- `config.py`: ports, topics, model paths, sample list, class sets, IDs, and simulated resource profiles
- `broker/app.py`: embedded MQTT 3.1.1 broker
- `edge/app.py`: YOLO11n inference, summaries, decision rule, and MQTT edge service
- `cloud/app.py`: Flask API, YOLO11m, MQTT handler, annotation, alerts, and SQLite
- `gateway/radio.py`: frame encryption, MIC, counters, fragmentation, and reassembly
- `gateway/network_server.py`: UDP decoding and MQTT publication
- `vibration/model.py`: tiny 1D CNN architecture
- `vibration/payload.py`: 29-byte binary payload codec
- `vibration/train_model.py`: reproducible synthetic checkpoint training
- `webots/worlds/edge1_camera_jetson.wbt`: Edge-1 Jetson Nano camera/YOLO scene
- `webots/worlds/edge2_vibration_device.wbt`: Edge-2 simple vibration-device/CNN scene
- `webots/controllers/camera_edge/`: Edge-1 camera capture, YOLO11n and uplink
- `webots/controllers/vibration_edge/`: Edge-2 generated vibration, CNN and uplink
- `webots/controllers/perimeter_gateway/`: shared radio-to-UDP relay controller
- `webots/controllers/scene_labels/`: world-specific legends and controls
- `sensor/mock_sensor.py`: optional direct MQTT camera publisher
- `cloud/templates/index.html`: dashboard markup
- `cloud/static/app.js`: browser requests, polling, and rendering; no ML
- `cloud/static/style.css`: dashboard styling
- `tests/test_models.py`: model, input, topic, policy, and profile checks
- `tests/test_uplink.py`: two-device radio, payload, integrity, fragmentation, and replay checks
- `docs/README.md`: operating and presentation guide
- `docs/DEMO_RUNBOOK.md`: concise startup, presentation, shutdown, and troubleshooting sequence
- `docs/IMPLEMENTATION.md`: code-grounded technical reference
- `docs/ARCHITECTURE_MAPPING.md`: mapping from proposed architecture to the working demonstration
- `docs/EDGE_LORAWAN_CLOUD_LOGS.md`: reproducible terminal/MQTT evidence guide
- `docs/IMAGE_TRANSFER_FLOW.md`: HTTP image path and compact-result transport boundary
- `docs/SENSOR_CORRELATION_IDEAS.md`: future camera/vibration incident-fusion options
- `docs/VIBRATION_MODEL_TRAINING.md`: synthetic training data, runtime values and evaluation limits

Treat `perimeter_events.db`, `.runtime/`, `__pycache__/`, logs, and `myenv/` as generated state. Preserve model checkpoints and the nine sample images.

## Validation

Run from this repository root:

```powershell
.\myenv\Scripts\python.exe -B -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m pip check
node --check cloud\static\app.js
```

The current suite has 14 Python tests. They cover model assets, separate Edge-1/Edge-2 worlds, sample images, answer-free input events, summaries, offloading, topic helpers, simulated profiles, the vibration checkpoint, independent radio devices/keys, the compact vibration payload, fragmentation, tampering, and replay rejection.

For a dashboard or service change, also perform an end-to-end run when feasible. In Webots mode, expect inference logs from `[edge]` and `[vibration-edge]`, transport logs from `[lorawan-tx]`, `[lorawan-payload]`, `[gateway]`, `[lorawan-rx]`, and `[network]`, then application results from `[cloud]`.

## Claims that must remain honest

- `edge` and `cloud` are logical roles. Both run on the same Windows laptop.
- The Webots Jetson Nano and 512 MB/2 W vibration profiles are descriptive metadata; they do not reserve resources or reproduce target performance.
- There is no CUDA, TensorRT, ARM, power, temperature, energy, or SCI measurement.
- The vibration signal and checkpoint training data are synthetic.
- The simulated uplink is not RF or a complete LoRaWAN network.
- Images use local HTTP, not MQTT payload bytes or LoRaWAN.
- The offloading rule is hand-written and not carbon-aware.
- MQTT is anonymous and unencrypted. Flask is a development server. This is not production security.
- Dashboard polling does not trigger inference.

## Maintenance rules

- Keep this final repository compact; do not create another application folder unless explicitly requested.
- Preserve separation from older sibling demos.
- Keep the UI and MQTT sample/upload events free of `expected_label` or other answer-revealing fields.
- Keep RGB bytes off MQTT and simulated LoRaWAN; use URL-based image transfer.
- Do not describe laptop CPU execution as Jetson hardware emulation.
- Update `README.md`, the relevant files in `docs/`, and this guide when commands, modes, ports, topics, models, routes, storage, or claims change.
- Avoid deleting user work. This checkout may not have Git metadata.
- Stop only processes started for validation and check for stale owners of TCP 1883/8000 and UDP 16803 before restarting.
- Run checks proportional to the change and state any verification limits.

## Handoff checklist

1. Confirm whether the change affects MQTT-only mode, Webots mode, or both.
2. Verify the documented command from this repository root.
3. Check required model/sample assets and affected ports.
4. Run the Python tests plus any relevant JavaScript or end-to-end checks.
5. Stop only validation processes you started.
6. Remove temporary test events/downloads without deleting retained source assets.
7. Reconcile `AGENTS.md` and the relevant indexed documentation with the resulting implementation.
