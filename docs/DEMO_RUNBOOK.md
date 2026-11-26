# Demo runbook: start, operate, explain, and stop the application

Use this file when you need to demonstrate the complete application without help. The recommended presentation is the **full Webots mode** because it starts the camera edge, vibration edge, simulated LoRaWAN gateway, MQTT broker, cloud service, database, and dashboard.

## 1. Use the correct project folder

Use the Git repository folder. On this machine it is:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security-main
```

If you clone the repository on another computer, change to that clone's folder and create a fresh virtual environment there. Virtual environments are machine-specific and are intentionally excluded from Git.

## 2. What the complete demo contains

| Component | Implementation | Purpose |
| --- | --- | --- |
| Local MQTT broker | `broker/app.py` | Carries camera requests, decoded edge results, status, and alerts. |
| Cloud/application server | `cloud/app.py` | Flask API/dashboard, YOLO11m, annotation, SQLite, and MQTT consumer. |
| Camera edge | Webots `camera_edge.py` in the Edge-1 world | Captures an RGB frame and runs YOLO11n first. |
| Vibration edge | Webots `vibration_edge.py` | Generates 64 accelerometer-like samples and runs the tiny 1D CNN. |
| Simulated gateway | Webots `perimeter_gateway.py` | Receives the two Webots radio channels and forwards frames over UDP. |
| Network server | `gateway/network_server.py` | Verifies/decrypts/reassembles uplinks and publishes application events to MQTT. |
| Web dashboard | `http://127.0.0.1:8000` | Accepts images and displays camera/vibration results. |
| Database | `perimeter_events.db` | Stores camera and vibration events locally. |

All neural-network inference currently runs on the Windows laptop CPU. Webots represents the edge devices and communication flow; it does not emulate Jetson GPU speed, ARM execution, energy, temperature, or physical LoRa radio behavior.

## 3. One-time setup

You need:

- Python installed on Windows;
- Webots R2025a installed;
- `yolo11n.pt` and `yolo11m.pt` in the project root;
- `vibration/tiny_vibration_cnn.pt` in the project;
- the Python packages in `requirements.txt`.

If `myenv` does not exist or is broken, create it from the project root:

```powershell
python -m venv myenv
.\myenv\Scripts\python.exe -m pip install -r requirements.txt
```

Do this before the presentation because installing PyTorch and Ultralytics can take time.

If the launcher cannot locate Webots automatically, set its executable path in the same PowerShell window:

```powershell
$env:PERIMETER_WEBOTS_EXE = "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"
```

Change the path if Webots is installed elsewhere.

## 4. Pre-demo check

Run these commands before the presentation:

```powershell
.\myenv\Scripts\python.exe -B -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m pip check
node --check cloud\static\app.js
```

Expected results:

- 15 Python tests pass;
- `pip check` prints `No broken requirements found`;
- the Node command produces no output when the JavaScript syntax is valid.

The Node check is optional if Node.js is not installed. Node.js is not required to run the application in a browser.

Make sure another copy is not already using the application ports:

```powershell
Get-NetTCPConnection -LocalPort 1883,8000 -State Listen -ErrorAction SilentlyContinue
```

No output means the ports are free. If a process appears, close the old demo terminal before starting another copy.

## 5. Start every component with one command

From the project root, run:

```powershell
.\myenv\Scripts\python.exe run_demo.py --webots
```

Do not separately start the broker, cloud, gateway, or Webots world. The launcher starts them in the correct order and creates fresh per-run session keys.

Wait until the terminal prints:

```text
RGB object-detection demo is running.
Dashboard:   http://127.0.0.1:8000
MQTT broker: 127.0.0.1:1883
Edge model:  YOLO11n (simulated Jetson Nano in Webots, executed on laptop CPU)
Sensor edge: Tiny 1D CNN (512 MB low-power profile, laptop CPU)
Cloud model: YOLO11m (laptop CPU)
```

The first launch may take longer while Webots opens and the YOLO models load. Do not press buttons until the ready message appears.

Open this page in a browser:

```text
http://127.0.0.1:8000
```

The dashboard should show the MQTT broker, camera edge, vibration edge, and cloud as online.

## 6. Recommended five-minute happy-path presentation

### Step 1: show the architecture starting

Show the terminal and briefly identify these messages:

```text
[broker] MQTT 3.1.1 listening on 127.0.0.1:1883
[cloud] YOLO11m subscribed to perimeter/edge/+/result
[network] gateway backhaul listening on UDP 16803
[vibration-edge] Tiny 1D CNN ready: 482 parameters
[edge] YOLO11n subscribed to perimeter/camera/+/image
```

Webots opens separate Edge-1 and Edge-2 worlds. Each has its own scene-label and gateway controller; Edge-1 runs the camera controller and Edge-2 runs the vibration controller. Both views reproduce the same `north-gate` fence coordinates and mark the other sensor's position.

### Step 2: show the automatic Webots camera event

The camera edge automatically captures one Webots frame after startup. It sees the shared brown `north-gate` fence and may classify the scene as `normal`; that is acceptable. Point out:

- the image is captured by the Webots camera;
- YOLO11n runs at the logical edge;
- only the inference result takes the simulated LoRaWAN path;
- the JPEG remains available over local HTTP because RGB images are too large for LoRaWAN.

Expected terminal sequence:

```text
[edge] webots-camera.jpg -> normal -> edge (... ms)
[lorawan-tx][edge-1] zone=north-gate ... payload=<bytes>B fragments=<count>
[lorawan-payload][edge-1] object=normal ... image_ref=HTTP_URL
[gateway][edge-1] forwarded=... -> UDP:16803
[lorawan-rx][edge-1] zone=north-gate ... fragments=<count>
[network] event=<event-id> -> MQTT perimeter/edge/simulated-edge-01/result
[cloud] <event-id> zone=north-gate -> edge -> normal
```

### Step 3: demonstrate a person or vehicle offload

On the dashboard, use one of these built-in inputs:

| Dashboard input | Intended content | Typical decision |
| --- | --- | --- |
| Sample 01 | normal scene | accepted at edge |
| Sample 02 | animal | accepted at edge if confident |
| Sample 03 | person | offloaded to cloud |
| Sample 04 | vehicle | offloaded to cloud |

Choose **Sample 03** or **Sample 04**, then press **Run detection**. Wait for the completed event to appear.

Explain the decision rule:

- YOLO11n always runs first;
- a person or vehicle is sent to YOLO11m for stronger cloud verification;
- any relevant detection below 50% confidence is also offloaded;
- a confident animal or no relevant object is accepted at the edge;
- OpenCV in the cloud service draws the final bounding boxes.

The sample name is the only browser selection sent. No expected answer label is provided to either model.

### Step 4: demonstrate the vibration edge

Click inside the Webots 3D window so it has keyboard focus, then press **V** once.

The vibration node collects a 64-sample window at 31.25 Hz. One window takes approximately 2.05 seconds. It runs a 482-parameter 1D CNN and sends a compact result. Every fourth window also contains an automatic anomaly, so normal and anomaly events appear even without pressing V.

Expected terminal sequence:

```text
[vibration-edge] window ... -> vibration_anomaly (...%, ... ms)
[lorawan-tx][edge-2] zone=north-gate ... payload=29B fragments=1
[lorawan-payload][edge-2] anomaly=YES ... compact_hex=...
[gateway][edge-2] forwarded=1 ... -> UDP:16803
[lorawan-rx][edge-2] zone=north-gate ... fragments=1 anomaly=YES
[network] event=<event-id> -> MQTT perimeter/edge/vibration-edge-01/result
[cloud] vibration <event-id> zone=north-gate -> vibration_anomaly (...%)
```

The event should appear in the dashboard's **Vibration sensor events** table with `north-gate`, classification, confidence, RMS, peak, and edge latency.

### Step 5: optionally demonstrate a new Webots frame or uploaded photograph

For another Webots camera capture, focus the Webots window and press **C** once.

For an external photograph, drag a JPG, PNG, or WebP file onto the dashboard or use its file selector. The maximum upload size is 8 MB. The server validates it, converts it to JPEG, and limits the longest side to 1600 pixels.

An uploaded image follows the same YOLO11n decision and optional YOLO11m verification path. It is kept only in memory for the current application run.

## 7. What data is sent at each stage

### Camera input

For a built-in dashboard sample, the browser initially sends only a key such as:

```json
{"image": "sample_03"}
```

The cloud API converts that into camera-event metadata similar to:

```json
{
  "event_id": "generated-uuid",
  "timestamp": "UTC timestamp",
  "camera_id": "rgb-camera-01",
  "zone": "north-gate",
  "image_name": "Sample 03",
  "image_url": "http://127.0.0.1:8000/static/demo_person.jpg",
  "source": "sample"
}
```

This metadata and URL are published to MQTT topic `perimeter/camera/<camera-id>/image`. Raw JPEG bytes are not placed in MQTT.

### Camera edge result

YOLO11n returns:

- summary: `normal`, `animal`, `person`, or `vehicle`;
- detected class and confidence;
- bounding-box coordinates;
- edge inference latency;
- chosen execution location and decision reason;
- simulated device and Webots position metadata when applicable.

In Webots mode, this result is encrypted and fragmented into local LoRaWAN 1.0-style ABP frames. It travels through Webots radio channel 40, the gateway, UDP port 16803, and then MQTT topic `perimeter/edge/<edge-id>/result`.

### Vibration input and result

The vibration controller generates 64 one-axis accelerometer-like samples. The raw sample window stays at the edge and is given to the 1D CNN.

Only a 29-byte binary result payload is sent. It contains:

- event UUID and timestamp;
- `normal` or `vibration_anomaly` class;
- confidence;
- RMS acceleration;
- peak acceleration;
- inference latency.

It travels through Webots radio channel 41 and the same gateway/network-server path. The cloud does not rerun the vibration model.

### Data stored by the cloud

SQLite stores camera summaries, detections, offload reason, latencies, sensor metadata, alert state, and annotated JPEG. A separate table stores vibration classifications, confidence, RMS, peak, latency, model information, and the simulated resource profile.

## 8. Complete happy-path flow

### Dashboard sample or upload

```text
Browser
  -> HTTP POST /api/run or /api/upload
  -> cloud creates camera metadata and temporary image URL
  -> MQTT camera topic
  -> Webots camera edge receives the event
  -> YOLO11n at 416 px on laptop CPU
  -> offload decision
  -> encrypted LoRaWAN-style Webots radio frames
  -> simulated gateway
  -> UDP 127.0.0.1:16803
  -> network server verifies MIC/counter, decrypts and reassembles
  -> MQTT edge-result topic
  -> cloud accepts edge result or runs YOLO11m at 640 px
  -> OpenCV draws final boxes
  -> SQLite stores event
  -> browser polling displays result
```

### Vibration event

```text
Synthetic accelerometer-like samples in Webots
  -> 64-sample window
  -> tiny 1D CNN at vibration edge
  -> 29-byte result payload
  -> encrypted LoRaWAN-style Webots radio frame
  -> simulated gateway
  -> UDP network server
  -> MQTT edge-result topic
  -> cloud stores event and publishes alert for anomaly
  -> browser displays vibration row
```

## 9. Normal terminal logs that are not inference

While the dashboard is open, the browser polls:

- `GET /api/status` every 3 seconds;
- `GET /api/events` every 2 seconds;
- `GET /api/vibration-events` every 2 seconds.

These Flask request lines are normal. They only refresh the page; they do not run YOLO or the vibration CNN. Actual inference and transport logs begin with `[edge]`, `[vibration-edge]`, `[lorawan-tx]`, `[lorawan-payload]`, `[gateway]`, `[lorawan-rx]`, `[network]`, or `[cloud]` and mention an event result.

## 10. Stop everything safely

Return to the PowerShell window that runs `run_demo.py` and press **Ctrl+C once**.

Wait for:

```text
Stopping demo...
```

The launcher closes Webots and its child services. Do not repeatedly press Ctrl+C while cleanup is running.

## 11. Fast recovery and troubleshooting

### The virtual environment points to a missing Python executable

Delete or move that generated environment, then recreate `myenv` using the setup commands in this file. Do not commit or copy a virtual environment between computers.

### `Webots was not found`

Set `PERIMETER_WEBOTS_EXE` to the full installed `webots.exe` path, then rerun the launcher.

### `ModuleNotFoundError`

Install all requirements into the environment used by the launcher:

```powershell
.\myenv\Scripts\python.exe -m pip install -r requirements.txt
```

### Address or port already in use

Another demo copy is probably running. Close its launcher/Webots window, confirm ports 1883 and 8000 are free, and start again.

### Dashboard remains on `WAITING FOR EDGE DEVICES`

Wait for the terminal ready message. Then check for `[edge] YOLO11n subscribed...` and `[vibration-edge] Tiny 1D CNN ready...`. If Webots was reset or closed separately, stop the whole launcher and restart it so session keys and frame counters are recreated together.

### Pressing C or V does nothing

Click inside the Webots 3D view first, then press the key once. Keyboard input is sent to the focused application.

### Webots camera result is `normal`

That is expected for the simple shared-fence scene. Use Sample 03, Sample 04, or an uploaded real image to demonstrate recognizable RGB object detection.

### First inference is slow

The first YOLO inference includes model warm-up and is normally slower. Run one sample before the audience arrives.

## 12. Plan B if Webots does not start

You can still demonstrate the original MQTT edge/cloud path:

```powershell
.\myenv\Scripts\python.exe run_demo.py
```

This starts the MQTT broker, Flask/cloud service, and logical YOLO11n edge process. The dashboard samples and uploads work, including conditional YOLO11m offloading. The vibration edge, simulated LoRaWAN gateway, and Webots scene are not active in this fallback mode.

## 13. Claims to make honestly during the presentation

- YOLO11n and YOLO11m are real pretrained object-detection models.
- The vibration CNN is real inference code but was trained on synthetic demonstration signals.
- Webots provides logical devices and radio transport; it does not emulate Jetson hardware performance or physical LoRa RF.
- The 4 GB/10 W Jetson and 512 MB/2 W vibration profiles are descriptive targets, not measured laptop resource use.
- The local LoRaWAN-style implementation demonstrates encryption, MIC, counters, fragmentation, gateway relay, and MQTT integration. It does not simulate RF propagation, frequencies, spreading factors, airtime, duty cycle, ADR, joins, or downlinks.
- MQTT is anonymous and local, Flask uses its development server, and there is no TLS. This is a college proof of concept, not production security.

For deeper implementation details, see `docs/IMPLEMENTATION.md`. For model and MQTT background, see `docs/README.md`.
