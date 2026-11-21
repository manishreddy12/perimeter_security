# Agent guide: Perimeter Security edge/cloud ML project

This file is the starting point for any coding agent or maintainer working in this workspace. Read it before changing either application, then read the application-specific `README.md` and `docs/README.md` files referenced below.

## Project goal

This is a college project demonstrating ML inference split between a logical edge device and a laptop acting as cloud infrastructure. The working communication path is MQTT. The long-term architecture also discusses LoRaWAN, gateways, real sensors, Jetson-class hardware, carbon-aware offloading, SCI calculations, metrics, and logging, but not all of those parts are implemented yet.

The workspace intentionally contains two separate demonstrations:

1. `perimeter_security_demo/` is the current and primary RGB object-detection application.
2. `perimeter_security_previous_demo/` preserves the previous synthetic 5×4 sensor-matrix prototype.

Do not mix their code, claims, model files, ports, databases, or datasets.

## Current primary application: RGB YOLO demo

Location: `perimeter_security_demo/`

### What it demonstrates

- A browser or mock camera creates an RGB image event.
- MQTT transports the event metadata and image URL.
- YOLO11n runs first at the logical edge.
- A risk/confidence rule chooses edge acceptance or cloud offload.
- YOLO11m runs on the laptop only for offloaded images.
- OpenCV draws the selected model's bounding boxes.
- SQLite stores events, detections, latency, decision reason, alert state, and the annotated JPEG.
- A local Flask dashboard shows samples, uploads, results, logs, and service state.

This is an execution-flow simulation, not a hardware or performance simulation. Both models currently run on the Windows laptop CPU. `edge` and `cloud` are separate logical services. A real Jetson target should use YOLO11n exported to TensorRT and measured on the physical GPU.

### Start command

From PowerShell:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security_demo
.\myenv\Scripts\python.exe run_demo.py
```

Open http://127.0.0.1:8000. Press `Ctrl+C` in the terminal to stop the launched services.

Default ports:

- MQTT broker: `127.0.0.1:1883`
- Flask dashboard/API: `127.0.0.1:8000`

The environment variables `PERIMETER_MQTT_HOST`, `PERIMETER_MQTT_PORT`, `PERIMETER_CLOUD_HOST`, and `PERIMETER_CLOUD_PORT` override these values.

### Service startup

`run_demo.py` is the main entry point. It starts these modules as separate processes, in order:

1. `broker.app`
2. `cloud.app`
3. `edge.app`

It waits for the MQTT broker, cloud health endpoint, and retained edge status before printing that the application is ready.

### Complete request and inference flow

```text
Browser Run detection
  -> HTTP POST /api/run
  -> cloud/app.py creates camera metadata
  -> immediate HTTP 202 Queued response
  -> MQTT perimeter/camera/<camera-id>/image
  -> broker/app.py forwards message
  -> edge/app.py downloads image from image_url
  -> YOLO11n, 416 px, confidence threshold 0.25, CPU
  -> edge offloading rule
  -> MQTT perimeter/edge/<edge-id>/result
  -> cloud/app.py receives edge result
       -> selected edge: accept YOLO11n detections
       -> selected cloud: rerun image with YOLO11m, 640 px, CPU
  -> OpenCV draws boxes from selected detections
  -> SQLite perimeter_events.db
  -> browser later polls GET /api/events and displays result
```

The initial `POST /api/run` does not wait for inference. The browser learns about the completed result through later polling.

### Input paths

Built-in sample:

- Browser sends only a neutral key such as `sample_03` to `POST /api/run`.
- `cloud/app.py::run_image()` constructs the camera event.
- Nine local images are available as `Sample 01` through `Sample 09`.
- The UI and MQTT event do not include a preset answer tag.

Browser upload:

- Browser sends image bytes to `POST /api/upload` over HTTP.
- Accepted formats are JPG, PNG, and WebP, up to 8 MB.
- `cloud/app.py::upload_image()` validates the file, limits the longest side to 1600 pixels, converts it to JPEG, and stores it only in memory.
- The resulting temporary HTTP URL is sent through MQTT; raw image bytes are not placed in MQTT.
- Uploads and uploaded-event records are intentionally not durable across application restarts.

Command-line mock camera:

```powershell
.\myenv\Scripts\python.exe -m sensor.mock_sensor --image sample_03 --count 1
```

`sensor/mock_sensor.py` bypasses `/api/run` and publishes camera metadata directly to MQTT.

### MQTT topics

Configured in `perimeter_security_demo/config.py`:

- Camera input subscription: `perimeter/camera/+/image`
- Edge results: `perimeter/edge/+/result`
- Component state: `perimeter/status/+/state`
- Alerts: `perimeter/alerts`
- Cloud completion message: `perimeter/cloud/<edge-id>/result`

MQTT uses QoS 1. The local broker permits anonymous connections because this is a local demonstration, not a production security configuration.

### What runs at the edge

File: `perimeter_security_demo/edge/app.py`

- Loads `yolo11n.pt` with the common Ultralytics `YOLO` Python class.
- Downloads the image from the event's `image_url`.
- Runs YOLO11n using `imgsz=416`, `conf=0.25`, and `device="cpu"`.
- Retains only configured COCO person, vehicle, and common-animal classes.
- Returns bounding-box coordinates, class, confidence, model, input size, and latency.
- Summarizes detections with priority `vehicle`, then `person`, then `animal`, otherwise `normal`.
- Makes the offloading decision.

Current offloading rule in `choose_location()`:

- `person` -> cloud
- `vehicle` -> cloud
- relevant detections with maximum confidence below `0.50` -> cloud
- confident animal -> edge
- no configured security detection -> edge

This is a hand-written rule. It is not an ML, SCI, energy, or carbon-aware offloading algorithm yet.

### What runs in the cloud

File: `perimeter_security_demo/cloud/app.py`

The cloud service always handles APIs, browser uploads, MQTT edge results, annotation, SQLite storage, and dashboard reads. The heavy cloud model runs only when the edge selects `cloud`.

- Loads `yolo11m.pt`.
- On offload, runs YOLO11m with `imgsz=640`, `conf=0.25`, and `device="cpu"`.
- If the edge result is accepted, does not run YOLO11m.
- Uses OpenCV in `annotate()` to draw rectangles and labels from the selected model's coordinates.
- Treats final `person` and `vehicle` summaries as alerts. An animal is currently not an alert.
- Stores records in generated `perimeter_events.db`.

YOLO produces bounding-box coordinates. The browser does not draw boxes. It displays the annotated Base64 JPEG created by the cloud service.

### Dashboard polling and idle terminal logs

Files: `cloud/static/app.js` and `cloud/app.py`

- Browser calls `GET /api/status` every 3 seconds.
- Browser calls `GET /api/events` every 2 seconds.
- These timers interleave, so Flask request logs may appear roughly every second while the page is open.
- These GET requests do not publish MQTT camera events and do not run either YOLO model.
- Closing the dashboard tab stops browser polling while the backend remains ready for MQTT events.
- `run_demo.py` also polls health/status briefly during startup only.

Actual inference logs begin with `[edge]` or `[cloud]` and mention the image/event result.

### Current RGB application file map

- `run_demo.py`: main launcher and readiness checks.
- `config.py`: shared ports, URLs, topics, model paths, samples, IDs, and class sets.
- `broker/app.py`: embedded aMQTT broker; routes messages only.
- `edge/app.py`: YOLO11n and offloading logic.
- `cloud/app.py`: Flask API, temporary upload store, YOLO11m, annotation, database, alerts, and MQTT result handler.
- `sensor/mock_sensor.py`: optional MQTT camera-event publisher.
- `cloud/templates/index.html`: dashboard markup.
- `cloud/static/app.js`: button/upload requests, polling, and rendering; no ML.
- `cloud/static/style.css`: dashboard styling.
- `cloud/static/*.jpg`: nine offline sample images.
- `tests/test_models.py`: current automated checks.
- `docs/README.md`: detailed request flow and presentation instructions.
- `perimeter_events.db`: generated runtime database; do not treat it as source data.
- `yolo11n.pt` and `yolo11m.pt`: required pretrained checkpoints; keep them unless model strategy changes intentionally.

### Validation commands

From `perimeter_security_demo/`:

```powershell
.\myenv\Scripts\python.exe -B -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m pip check
node --check cloud\static\app.js
```

There are currently seven Python tests covering weights, samples, topics, summaries, offloading, and answer-free preset/upload events.

### RGB application facts that must remain honest

- YOLO11n and YOLO11m are different model scales loaded through the same Ultralytics `YOLO` class.
- Local weights are approximately 5.6 MB and 40.7 MB respectively.
- The edge is presently Windows CPU simulation, not Webots and not a Jetson GPU.
- The same Python approach can be moved to Jetson, but TensorRT export, CUDA device selection, and physical measurement remain future work.
- COCO benchmark performance is not the same as accuracy at the intended perimeter site.
- The dashboard samples and user uploads do not provide ground-truth evaluation labels.

## Previous application: synthetic 5×4 sensor-matrix demo

Location: `perimeter_security_previous_demo/`

This folder preserves the earlier prototype. It is not the active RGB application.

### Start and retrain commands

It reuses the RGB demo's installed environment:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security_previous_demo
..\perimeter_security_demo\myenv\Scripts\python.exe app.py
```

Open http://127.0.0.1:8001.

Retrain:

```powershell
..\perimeter_security_demo\myenv\Scripts\python.exe train_models.py
```

Default ports:

- MQTT broker: `127.0.0.1:1884`
- Flask dashboard/API: `127.0.0.1:8001`

### 5×4 input

Each example has five time samples at 250 ms intervals and four columns:

1. PIR motion: 0 or 1
2. Vibration RMS: g
3. Distance: metres
4. Thermal difference above ambient: degrees Celsius

The 20 normalized values are flattened before inference.

### Previous models

- Edge: custom binary logistic regression, `normal` versus `intrusion`.
- Cloud: custom NumPy MLP with architecture 20 -> 32 ReLU -> 4 softmax outputs.
- Cloud classes: `normal`, `person`, `animal`, and `vehicle`.
- Checkpoints are `models/edge_binary.npz` and `models/cloud_multiclass.npz`.
- These are locally trained custom models, not external pretrained models.

### Synthetic data and source-of-truth limitation

`train_models.py` generates the features and labels from hand-written distributions. The visible files are:

- `data/train.csv`: 2,800 balanced examples, seed 101.
- `data/validation.csv`: 600 balanced examples, seed 202.
- `data/test.csv`: 600 balanced examples, seed 303.
- `data/metadata.json`: feature, unit, split, seed, and provenance metadata.
- `models/evaluation.json`: validation/test metrics and confusion matrices.

The split and evaluation pipeline is reproducible, but there is no independent physical source of truth. Labels originate from the same generator that creates the features. Test performance measures consistency with synthetic rules, not real person/animal/vehicle accuracy.

Current reproducible held-out results:

- Edge test accuracy: 99.67%; macro F1: 99.55%.
- Cloud test accuracy: 93.5%; macro F1: 93.51%.
- Most cloud errors are person/animal confusions.

Never present these numbers as real-world field accuracy. This prototype demonstrates data flow, MQTT, edge filtering, cloud classification, and evaluation mechanics only. Real validation requires synchronized physical sensors and an independent label source such as video/manual observation, with splits by session, day, site, and device.

### Previous application file map

- `app.py`: combined local broker, edge model, cloud model, Flask API, SQLite, and dashboard.
- `train_models.py`: synthetic generator, CSV export, split management, training, selection, and evaluation.
- `templates/index.html`: compact dashboard.
- `data/`: generated but intentionally retained reproducible synthetic dataset artifacts.
- `models/`: generated but intentionally retained small model/evaluation artifacts.
- `docs/README.md`: complete training, matrix, metrics, viva answers, and limitations.
- `sensor_events.db`: generated runtime database if the application has been run.

## LoRaWAN and gateway status

LoRaWAN is an architectural requirement/future path, not a working part of either current demo.

- RGB images are too large for practical LoRaWAN transport.
- In a physical design, the edge should run image inference locally.
- LoRaWAN may carry compact detections, confidence, alerts, IDs, timestamps, status, or supporting scalar-sensor readings.
- Selected images should use Wi-Fi, Ethernet, cellular, or another IP path.
- A real LoRaWAN path requires radio end devices, a LoRaWAN gateway, a network server, and MQTT/application integration.
- The MQTT broker is not a LoRaWAN gateway.
- Any empty `gateway/` folder is a placeholder only; do not claim a gateway is implemented.

## Resource documents

`Resources/` contains project references and planning material, not runtime dependencies:

- `SCI for ML Inferencing.pdf`: original SCI/ML-inference slides; the last slides motivated the project.
- `Permieter-Security-IoT-case-study-IIITB-UEAU.pdf`: perimeter-security case-study material.
- `Energy-SLA-Aware Task Offloading.pdf`: offloading reference.
- `PERIMETER_SECURITY_ARCHITECTURE.md`: broader proposed architecture and future work.
- `MEETING_SPEECH.md`: presentation material.
- `EDGE_DEVICE_AND_MODEL_OPTIONS.md`: hardware/model options and staged plan.

When implementation and resource documents disagree, describe the implementation truth first and label resource material as planned architecture.

## Maintenance rules

- Keep the project compact. The user prefers a working college-project structure over excessive folders or abstractions.
- Do not create another application folder unless explicitly requested.
- Preserve the separation between the RGB demo and previous synthetic demo.
- Update the relevant `README.md`, `docs/README.md`, and this `AGENTS.md` when behavior, commands, ports, models, topics, or claims change.
- Do not reintroduce an `expected_label` or content-revealing tag into RGB sample/upload MQTT events.
- Do not send raw RGB bytes through MQTT; keep URL-based transfer in the demo.
- Do not imply that browser polling triggers inference. It only reads status/events.
- Do not call the laptop CPU edge service Webots, Jetson, or hardware emulation.
- Do not claim LoRaWAN, a gateway, SCI calculation, carbon-aware scheduling, real energy measurement, authentication, TLS, or production security is implemented unless code and tests are added.
- Treat `*.db`, caches, logs, virtual environments, and uploads as generated runtime state.
- Preserve `*.pt`, the nine sample JPG files, previous-demo CSVs, `*.npz`, and evaluation JSON because the demos depend on them or use them as evidence.
- Avoid deleting or overwriting user work. This workspace may not be initialized as a Git repository.
- Run tests proportional to each change and report any verification limits honestly.

## Quick handoff checklist

Before declaring a change complete:

1. Confirm which demo is in scope.
2. Verify the documented run command.
3. Check that ports are not occupied by stale demo processes.
4. Run the relevant Python tests or direct inference check.
5. For dashboard changes, validate the HTTP route, JavaScript syntax, and end-to-end MQTT path when feasible.
6. Stop only processes started for testing.
7. Remove temporary downloads and generated test databases/events.
8. Update application docs and this guide if architecture or behavior changed.

