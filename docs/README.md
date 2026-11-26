# Perimeter Security demonstration guide

This is the operating and presentation guide for the final project in `perimeter_security-main`. For source-level details, schemas, protocols, and limitations, see [IMPLEMENTATION.md](IMPLEMENTATION.md).

## Documentation map

Use each document for a specific purpose:

| Document | Purpose |
| --- | --- |
| [README.md](README.md) | Setup, run commands, demonstration sequence and troubleshooting |
| [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) | Concise presentation-day startup, happy path, shutdown and recovery sequence |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Complete code-grounded technical reference |
| [ARCHITECTURE_MAPPING.md](ARCHITECTURE_MAPPING.md) | Map the working demo to the proposed architecture and presentation terminology |
| [EDGE_LORAWAN_CLOUD_LOGS.md](EDGE_LORAWAN_CLOUD_LOGS.md) | Show terminal and MQTT evidence from edge through gateway/network server to cloud |
| [IMAGE_TRANSFER_FLOW.md](IMAGE_TRANSFER_FLOW.md) | Explain and demonstrate the separate HTTP image path |
| [SENSOR_CORRELATION_IDEAS.md](SENSOR_CORRELATION_IDEAS.md) | Explain current sensor independence and possible future fusion |
| [VIBRATION_MODEL_TRAINING.md](VIBRATION_MODEL_TRAINING.md) | Synthetic data, CNN training, runtime values and evaluation limits |

## What this project demonstrates

The project runs real neural-network inference while simulating where the work would execute in a physical perimeter system:

- YOLO11n examines every RGB event at a logical edge.
- A risk/confidence rule decides whether to accept that result or request cloud verification.
- YOLO11m runs on the laptop only for events selected for cloud verification.
- An optional Webots mode adds a camera node, a separate vibration edge with a 482-parameter 1D CNN, and a simulated radio gateway.
- MQTT connects application services; Flask provides the local dashboard/API; SQLite stores completed events.

All inference currently executes on the Windows laptop CPU. The words *edge*, *cloud*, and *Jetson Nano* describe logical placement and a simulated target profile. They do not mean that Jetson hardware, ARM, CUDA, TensorRT, physical radio, energy measurement, or field sensors are emulated.

## Quick start

### MQTT-only RGB mode

Open PowerShell:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security-main
.\myenv\Scripts\python.exe run_demo.py
```

Wait for:

```text
RGB object-detection demo is running.
```

Then open http://127.0.0.1:8000. This mode starts the embedded broker, Flask/cloud process, and logical RGB edge process. It does not start Webots, vibration inference, the network server, or UDP backhaul.

The page always contains a vibration section. In MQTT-only mode that device is absent, and the current combined status banner can remain `WAITING FOR EDGE DEVICES` even when RGB inference is ready. The launcher ready message and the RGB edge entry from `GET /api/status` are the relevant readiness indicators.

### Full Webots mode

Install Webots R2025a, then run:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security-main
.\myenv\Scripts\python.exe run_demo.py --webots
```

If the launcher cannot locate Webots:

```powershell
$env:PERIMETER_WEBOTS_EXE = 'C:\path\to\Webots\webots.exe'
.\myenv\Scripts\python.exe run_demo.py --webots
```

Webots opens two R2025a worlds and Edge-1 takes one initial camera capture. Both views contain the same `north-gate` fence at the same coordinates, with a camera position and a fence-mounted vibration-sensor position. Each view marks the other edge's location. This demonstrates two sensor perspectives on one area; the worlds still run as independent Webots processes. Click the relevant 3D view before using its keyboard control:

- Edge-1 camera world, `C`: take another camera capture
- Edge-2 vibration world, `V`: inject a synthetic vibration disturbance

Every fourth vibration window also receives an automatic demonstration disturbance. Each world has a fixed legend for its edge device, gateway relay, monitored object and keyboard control.

### Stop the application

Focus the launching PowerShell window and press `Ctrl+C` once. Wait for `Stopping demo...` while the launcher closes its process tree. Additional interrupts are ignored during cleanup.

## First-time setup

The project has been verified with Python 3.13. For a fresh environment:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security-main
py -3.13 -m venv myenv
.\myenv\Scripts\python.exe -m pip install -r requirements.txt
```

A virtual environment records the absolute path of its base interpreter and should be treated as generated, machine-local state. If the copied `myenv` reports `No Python at ...`, preserve it under another name and rebuild it:

```powershell
Move-Item -LiteralPath .\myenv -Destination .\myenv.stale
py -3.13 -m venv myenv
.\myenv\Scripts\python.exe -m pip install -r requirements.txt
```

Use a different backup name if `myenv.stale` already exists. Editing `myenv\pyvenv.cfg` is not a reliable repair.

Keep these local model assets in the repository root:

- `yolo11n.pt`
- `yolo11m.pt`
- `vibration/tiny_vibration_cnn.pt` for Webots mode

The nine offline sample JPEGs under `cloud/static/` are also required by the dashboard and tests.

## Execution modes at a glance

| Capability | MQTT-only mode | Webots mode |
| --- | --- | --- |
| Embedded MQTT broker | Yes | Yes |
| Flask dashboard/API and SQLite | Yes | Yes |
| YOLO11n RGB edge | Separate Python process | Webots controller process |
| YOLO11m cloud verification | Yes | Yes |
| Webots 3D scenes | No | Yes, separate Edge-1 and Edge-2 worlds |
| Vibration 1D CNN | No | Yes |
| Simulated LoRaWAN result uplink | No | Yes |
| UDP gateway backhaul | No | Yes, localhost port 16803 |

Both modes execute all ML on the same Windows laptop CPU.

## RGB request flow

### Built-in sample or browser upload

```text
Browser
  -> POST /api/run with a neutral sample key
     or POST /api/upload with image bytes
  -> HTTP 202 Queued
  -> MQTT camera event containing metadata and image_url
  -> YOLO11n at 416 px
  -> hand-written offloading rule
  -> MQTT directly in default mode
     or simulated radio -> gateway -> UDP -> MQTT in Webots mode
  -> accept edge boxes or run YOLO11m at 640 px
  -> OpenCV annotation -> SQLite
  -> browser later polls GET /api/events
```

The input request does not wait for detection. The browser shows the result after a later poll. Status and event polling never trigger either YOLO model.

The built-in cards send only keys such as `sample_03`; the service creates neutral names such as `Sample 03`. Neither built-in nor uploaded events contain `expected_label`, a user-provided object class, or another answer tag.

### Upload behavior

The UI accepts JPG, PNG, and WebP images up to 8 MB. The server verifies that OpenCV can decode the bytes, resizes the image if its longest side exceeds 1600 pixels, converts it to JPEG, and stores at most 20 converted uploads in memory.

MQTT receives only a temporary local HTTP URL plus metadata. Raw JPEG bytes do not travel through MQTT or the simulated radio. Uploaded images and their database event rows are intentionally removed across an application restart because their URLs are no longer valid.

### Command-line camera publisher

With the application running:

```powershell
.\myenv\Scripts\python.exe -m sensor.mock_sensor --image sample_03 --count 1
```

Use `--image cycle` to rotate through all samples. The default `--count 0` publishes until interrupted. This utility publishes directly to MQTT and bypasses `POST /api/run`.

## Edge and cloud decisions

YOLO11n runs first with a 416-pixel input, confidence threshold 0.25, and CPU device. The service retains configured COCO people, vehicles, and common animals.

| Edge output | Action |
| --- | --- |
| Person | Run YOLO11m |
| Vehicle | Run YOLO11m |
| Retained detections with maximum confidence below 0.50 | Run YOLO11m |
| Confident animal | Accept YOLO11n |
| No configured security object | Accept YOLO11n |

YOLO11m uses a 640-pixel input, confidence threshold 0.25, and CPU device. It is skipped when the edge decision is accepted. A final `person` or `vehicle` summary creates an alert; `animal` currently does not.

YOLO supplies the bounding-box coordinates. `cloud/app.py` uses OpenCV to draw the selected model's boxes and stores an annotated Base64 JPEG. The browser displays that image; it does not calculate or draw boxes itself.

The offloading decision is a hand-written policy. It is not learned, SLA-aware, carbon-aware, or based on SCI or measured energy.

## Webots camera path

The green Edge-1 camera controller:

1. waits for its MQTT status/input connection;
2. captures an initial Webots frame, or another frame after `C`;
3. posts the JPEG to `POST /api/webots/capture` for temporary HTTP storage;
4. runs YOLO11n on the already captured frame;
5. attaches the simulated GPS position and descriptive 4 GB/10 W Jetson Nano profile;
6. sends the compact result over Webots radio channel 40.

The Edge-1 world's blue gateway relay forwards radio frames to UDP `127.0.0.1:16803`. The Python network server verifies and reconstructs the event, then publishes it to the normal MQTT edge-result topic. The cloud service performs the same optional YOLO11m, annotation, alert, and database stages as in default mode.

The image itself stays on local HTTP. Only the inference result and metadata use the simulated radio path.

## Webots vibration path

The fixed orange Edge-2 node in its own world generates reproducible one-axis synthetic samples rather than reading physical motion. Each non-overlapping window contains 64 samples at 31.25 Hz, or about 2.05 seconds.

The tiny model is:

```text
Conv1d(1, 8, kernel 5) -> ReLU -> MaxPool1d(2)
  -> Conv1d(8, 16, kernel 3) -> ReLU
  -> AdaptiveAvgPool1d(1) -> Linear(16, 2)
```

It has 482 parameters and predicts `normal` or `vibration_anomaly`. Its 29-byte binary result fits in one simulated uplink frame on channel 41. An anomaly creates an alert and appears in the vibration table.

The checkpoint was trained on generated signals, and the metadata's training score was measured on that generated training set. It is not physical-site accuracy and has no independent held-out field evaluation. To reproduce the checkpoint:

```powershell
.\myenv\Scripts\python.exe -m vibration.train_model
```

Retraining intentionally overwrites the vibration checkpoint and metadata; do it only when that change is intended.

## Simulated LoRaWAN boundary

Webots mode implements a local LoRaWAN 1.0-style ABP uplink demonstration with:

- two device addresses and independent per-launch session keys;
- encrypted application payloads and AES-CMAC integrity;
- frame counters, replay rejection, and large-gap rejection;
- application-specific fragmentation/reassembly;
- 64-byte maximum Webots radio frames and 43 application bytes per fragment.

It does not implement physical RF, regional settings, join procedures, downlinks, adaptive data rate, spreading factors, airtime, duty cycle, coverage, or a physical gateway. Restart the complete launcher after resetting either Webots world so frame counters and per-run keys agree.

## MQTT topics

All application messages use QoS 1.

| Topic | Producer | Consumer | Content |
| --- | --- | --- | --- |
| `perimeter/camera/+/image` | Flask or mock camera | RGB edge | Metadata and image URL |
| `perimeter/edge/+/result` | Edge or network server | Cloud | Camera or vibration inference result |
| `perimeter/status/+/state` | Edge/cloud components | Cloud/dashboard | Retained service state and profile |
| `perimeter/alerts` | Cloud | Optional subscriber | Final alert event |
| `perimeter/cloud/<edge-id>/result` | Cloud | Optional subscriber | Compact RGB completion event |

The local `amqtt` broker permits anonymous connections and has no TLS. This is acceptable only for the localhost demonstration, not a production deployment.

## Dashboard and storage

The dashboard shows:

- nine neutral offline samples and an upload drop zone;
- original and annotated images;
- edge and final summaries, box counts, decision reason, location, and latency;
- recent camera and vibration event tables;
- derived application logs and component status.

Polling intervals are:

- `/api/status`: 3 seconds
- `/api/events`: 2 seconds
- `/api/vibration-events`: 2 seconds

SQLite file `perimeter_events.db` contains `events` and `vibration_events`. It is generated runtime state, not source data or an evaluation dataset. The `Clear events` button calls unauthenticated `POST /api/reset`, deletes both tables' rows, and clears in-memory images.

## Presentation sequence

### Short MQTT-only demonstration

1. Start `run_demo.py` and wait for the ready message.
2. Open the dashboard.
3. Run an animal/normal sample to show edge acceptance.
4. Run a person/vehicle sample to show YOLO11m verification.
5. Upload an image and point out that no class answer is requested.
6. Explain that polling reads completed data and does not trigger inference.
7. Stop with one `Ctrl+C`.

### Full Webots demonstration

1. Start `run_demo.py --webots` and wait for both edge services.
2. Show the separate Edge-1 and Edge-2 Webots worlds and the initial camera event.
3. Focus Edge-1 and press `C`; follow `[edge]`, `[lorawan-tx]`, `[lorawan-payload]`, `[gateway]`, `[lorawan-rx]`, `[network]`, and `[cloud]` logs.
4. Focus Edge-2 and press `V`; show the same payload stages and the `north-gate` vibration dashboard row.
5. Explain that compact results use simulated radio while images use local HTTP.
6. State explicitly that target resource profiles are metadata and measured latency is laptop latency.
7. Stop from the launching PowerShell window.

The first YOLO inference can be slower while PyTorch initializes CPU kernels.

## Validation

From the repository root:

```powershell
.\myenv\Scripts\python.exe -B -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m pip check
node --check cloud\static\app.js
```

The current Python suite contains 14 tests covering required assets, the separate edge worlds, neutral inputs, summaries and offloading, profiles, the vibration checkpoint, separate radio devices/keys, payload size, fragmentation, tampering, and replay rejection.

## Troubleshooting

- **Port 1883 or 8000 is busy:** stop an older launcher/service process before retrying.
- **UDP 16803 is busy in Webots mode:** stop the stale network-server process.
- **Launcher cannot find Webots:** set `PERIMETER_WEBOTS_EXE` to the R2025a executable.
- **Dashboard says waiting in MQTT-only mode:** vibration is not started in that mode; check the terminal ready message and `edge.status` from `/api/status`.
- **No relevant object is shown:** only configured person, vehicle, and common-animal COCO classes are retained.
- **Upload fails:** use a readable JPG, PNG, or WebP under 8 MB.
- **Webots result is rejected after a world reset:** restart the complete launcher to refresh keys and counters.
- **Page requests keep appearing in the terminal:** close the dashboard tab to stop its 2-second/3-second polling. These GETs are not inference.
- **Missing package:** run `.\myenv\Scripts\python.exe -m pip install -r requirements.txt`.

## Honest project claims

- The RGB models are pretrained YOLO11n and YOLO11m scales; the vibration model is a separately trained tiny synthetic-data CNN.
- All inference runs on the Windows laptop CPU.
- The Webots nodes and their 4 GB/10 W and 512 MB/2 W profiles are logical/simulated descriptions.
- COCO benchmark results are not deployment-site accuracy.
- Vibration training accuracy is not field accuracy.
- LoRaWAN behavior is a local encrypted-frame demonstration, not measured RF.
- There is no physical power, energy, temperature, SCI, or carbon-aware scheduler.
- MQTT and Flask are configured for a local demonstration, not production security.

## Moving toward physical deployment

A physical version should export YOLO11n to TensorRT on the target Jetson, select the CUDA/TensorRT runtime there, acquire real camera and vibration data, use a real LoRaWAN end device/gateway/network server only for compact results, transfer selected images over an IP-capable link, add authentication/TLS, and measure latency and energy on the actual hardware before reporting SCI or performance results.
