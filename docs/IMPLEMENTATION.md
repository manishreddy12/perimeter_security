# Perimeter Security implementation reference

## 1. Purpose and repository boundary

This document describes the code in the final `perimeter_security-main` repository: its processes, inference stages, communication paths, storage, APIs, simulator integration, tests, and limitations.

The implementation is a functional local demonstration. All neural-network inference executes on the Windows laptop CPU. Webots provides a 3D world, logical devices, and packet transport; it does not emulate NVIDIA Jetson execution, sensor physics, LoRa RF, target-device power, or deployment-site accuracy.

Older prototypes that may exist elsewhere in the parent workspace are not runtime dependencies and are outside this document.

## 2. Implemented system

The final application has three ML roles:

| Role | Model | Execution condition | Actual host |
| --- | --- | --- | --- |
| RGB edge | YOLO11n, 416-pixel input | Every valid RGB event | Windows laptop CPU |
| RGB cloud verification | YOLO11m, 640-pixel input | Only when the edge rule selects `cloud` | Windows laptop CPU |
| Vibration edge | 482-parameter 1D CNN, 64 samples | Every Webots vibration window | Windows laptop CPU |

Supporting infrastructure includes:

- an embedded MQTT 3.1.1 broker;
- a Flask development server and browser dashboard;
- an SQLite runtime database;
- OpenCV image validation and annotation;
- and, in Webots mode, simulated radio nodes, a UDP gateway backhaul, and a Python network server.

## 3. Execution modes and lifecycle

### 3.1 Default MQTT-only mode

Command from the repository root:

```powershell
.\myenv\Scripts\python.exe run_demo.py
```

The launcher starts:

1. `python -u -m broker.app`
2. `python -u -m cloud.app`
3. `python -u -m edge.app`

Readiness is checked in this order:

1. connect to the MQTT broker;
2. call `GET /api/health`;
3. poll `GET /api/status` until the RGB edge status is `online`.

The default mode does not start Webots, `gateway.network_server`, the vibration controller, or UDP port 16803.

The dashboard JavaScript currently considers the whole page online only when MQTT, RGB edge, and vibration edge are all online. Therefore, its combined banner can remain `WAITING FOR EDGE DEVICES` in default mode even though the launcher is ready and RGB inference is functional. This is a front-end status condition, not an inference dependency.

### 3.2 Webots mode

Command:

```powershell
.\myenv\Scripts\python.exe run_demo.py --webots
```

The launcher locates Webots from `PERIMETER_WEBOTS_EXE`, `PATH`, or the normal Windows installation directory and starts:

1. `broker.app`
2. `cloud.app`
3. `gateway.network_server`
4. Webots in batch/realtime mode with `webots/worlds/edge1_camera_jetson.wbt`
5. Webots in batch/realtime mode with `webots/worlds/edge2_vibration_device.wbt`

The R2025a worlds assign these controllers:

| World | Controller | World object | Responsibility |
| --- | --- | --- | --- |
| Edge-1 | `scene_labels` | Supervisor | Camera-world legend and `C` instruction |
| Edge-1 | `camera_edge` | Green Jetson Nano profile | Camera capture, YOLO11n, camera-result uplink |
| Edge-1 | `perimeter_gateway` | Blue gateway relay | Channel 40 reception and UDP forwarding |
| Edge-2 | `scene_labels` | Supervisor | Vibration-world legend and `V` instruction |
| Edge-2 | `vibration_edge` | Orange simple device | Synthetic samples, 1D CNN, vibration-result uplink |
| Edge-2 | `perimeter_gateway` | Blue gateway relay | Channel 41 reception and UDP forwarding |

The two visible relays represent one logical gateway path: both send received frames to the same UDP network server on port 16803.

Both worlds reproduce the same `north-gate` scene coordinates: the brown fence is at `(3, 0, 1)`, the camera position is `(0, 0, 1)`, and the vibration sensor position is `(2.82, -0.75, 0.8)`. The world that does not execute a device shows a passive reference marker at its position. This aligns the sensor narratives spatially but does not synchronize the two Webots physics processes or correlate their events.

The launcher assigns Webots controller ports 1234 and 1235 explicitly so both simulator instances can run together without automatic port fallback.

Before those processes start, the launcher creates four random 16-byte session keys in environment variables:

- `PERIMETER_NWK_SKEY`
- `PERIMETER_APP_SKEY`
- `PERIMETER_VIBRATION_NWK_SKEY`
- `PERIMETER_VIBRATION_APP_SKEY`

It waits up to 150 seconds for both RGB and vibration retained statuses. The Edge-1 camera controller performs one initial capture after its MQTT connection is established.

### 3.3 Shutdown

`Ctrl+C` in the launcher enters cleanup and ignores subsequent SIGINTs. On Windows, `taskkill /T /F` stops each launched process tree in reverse order. On other platforms, the launcher sends normal process termination and escalates to kill after a timeout.

Before restarting after an abnormal exit, check for stale owners of TCP 1883, TCP 8000, and—when using Webots—UDP 16803.

## 4. Configuration and assets

`config.py` is the shared source for ports, topics, IDs, model paths, sample metadata, class groups, and simulated resource profiles.

| Setting | Default |
| --- | --- |
| MQTT | `127.0.0.1:1883` |
| Flask | `127.0.0.1:8000` |
| UDP backhaul | `127.0.0.1:16803` |
| RGB edge ID | `simulated-edge-01` |
| Vibration edge ID | `vibration-edge-01` |
| Camera radio device | `da1b0126` |
| Vibration radio device | `da1b0226` |
| MQTT QoS | 1 |

Network settings can be overridden with `PERIMETER_MQTT_HOST`, `PERIMETER_MQTT_PORT`, `PERIMETER_CLOUD_HOST`, and `PERIMETER_CLOUD_PORT`.

Required assets are:

- `yolo11n.pt`, approximately 5.6 MB;
- `yolo11m.pt`, approximately 40.7 MB;
- nine JPEGs configured in `DEMO_IMAGES`;
- and `vibration/tiny_vibration_cnn.pt` for Webots mode.

The launcher sets `YOLO_CONFIG_DIR` to `.runtime/ultralytics`.

## 5. RGB input paths

### 5.1 Built-in sample

The browser calls:

```http
POST /api/run
Content-Type: application/json

{"image":"sample_03"}
```

The API validates the key, constructs a camera event, publishes it to `perimeter/camera/rgb-camera-01/image`, and returns HTTP 202 with an event ID. The nine configured samples have neutral titles and descriptions.

Representative event:

```json
{
  "event_id": "uuid",
  "timestamp": "UTC ISO-8601",
  "camera_id": "rgb-camera-01",
  "zone": "north-gate",
  "image_name": "Sample 03",
  "image_url": "http://127.0.0.1:8000/static/demo_person.jpg",
  "source": "sample"
}
```

There is no `expected_label`, answer class, or user-entered object tag.

### 5.2 Browser upload

`POST /api/upload` reads at most 8 MB plus one sentinel byte, decodes with OpenCV, limits the longest side to 1600 pixels, and JPEG-encodes at quality 90. The UI advertises JPG, PNG, and WebP; the backend's actual validity test is whether OpenCV can decode the content.

The converted bytes are stored in an in-memory `OrderedDict` under a random ID. The store retains at most 20 items and evicts the oldest. The camera event uses ID `browser-upload`, source `upload`, and `GET /uploads/<id>` as its image URL.

Only the URL and metadata enter MQTT. Raw image bytes do not.

### 5.3 Webots capture

`POST /api/webots/capture` uses the same image preparation function with camera ID `webots-camera`, but it returns HTTP 201 with the camera event instead of publishing it to MQTT. The controller already owns the captured frame and calls `EdgeVisionModel.predict_frame()` locally.

The controller adds `sensor_readings` containing:

- Webots `GPS.getValues()` Cartesian position in metres;
- descriptive device name;
- simulated power-mode metadata;
- simulated memory metadata.

These values are scene/profile metadata, not real geographic GPS, power, or memory measurements.

### 5.4 Mock camera

`sensor/mock_sensor.py` builds the same kind of sample event and publishes directly to the configured camera topic. It does not call the Flask input routes.

## 6. RGB edge inference

`edge/app.py::EdgeVisionModel` loads `yolo11n.pt` through the Ultralytics `YOLO` class. Inference uses:

```python
model.predict(image, imgsz=416, conf=0.25, device="cpu", verbose=False)
```

Only these configured COCO groups are retained:

- person: `person`
- vehicle: `car`, `motorcycle`, `bus`, `truck`
- animal: `bird`, `cat`, `dog`, `horse`, `sheep`, `cow`, `elephant`, `bear`, `zebra`, `giraffe`

Each retained result has `class`, rounded `confidence`, and `[x1, y1, x2, y2]` coordinates. Summary priority is vehicle, person, animal, normal.

`choose_location()` implements:

| Edge result | Selected location | Reason category |
| --- | --- | --- |
| Person | Cloud | Security-sensitive |
| Vehicle | Cloud | Security-sensitive |
| Retained detections and maximum confidence below 0.50 | Cloud | Low confidence |
| Confident animal | Edge | Edge result sufficient |
| No retained security object | Edge | Edge result sufficient |

The outgoing edge envelope contains the original camera event, YOLO11n result, decision, and edge runtime/profile status.

In default mode, the service publishes that envelope directly to `perimeter/edge/simulated-edge-01/result`. In Webots mode, `publish_result` places it on a controller queue for simulated radio transmission.

## 7. RGB cloud processing

`cloud.app` loads `yolo11m.pt` at process startup. It subscribes to all edge-result and component-status topics.

For a camera edge result:

1. Duplicate `event_id` values already in SQLite are ignored.
2. If `selected_location` is `cloud`, the service downloads the image and runs:

   ```python
   cloud_model.predict(image, imgsz=640, conf=0.25, device="cpu", verbose=False)
   ```

3. If `selected_location` is `edge`, YOLO11m is not called; the service downloads the image only for annotation.
4. The chosen detections are summarized.
5. OpenCV draws rectangles and confidence labels and adds the selected model name.
6. The JPEG is encoded at quality 82 and stored as Base64.
7. SQLite receives the record.
8. A compact completion object is published to `perimeter/cloud/simulated-edge-01/result`.
9. A final person or vehicle also publishes to `perimeter/alerts`.

An animal result is not currently an alert. The fixed `north-gate` string is event metadata; the code does not perform geometric zone or authorization analysis.

## 8. Complete RGB flows

### 8.1 Default mode

```text
POST /api/run or /api/upload
  -> HTTP 202 after MQTT publication
  -> perimeter/camera/<camera-id>/image
  -> broker forwards message
  -> edge downloads image and runs YOLO11n
  -> perimeter/edge/simulated-edge-01/result
  -> cloud accepts edge output or runs YOLO11m
  -> OpenCV + SQLite + optional alert
  -> GET /api/events polling displays completion
```

### 8.2 Webots mode

```text
Webots camera or browser/MQTT camera event
  -> YOLO11n in Edge-1 camera_edge controller process
  -> Webots Emitter channel 40
  -> Webots gateway Receiver
  -> UDP 127.0.0.1:16803
  -> gateway.network_server decoder
  -> perimeter/edge/simulated-edge-01/result
  -> normal cloud processing
```

For a Webots capture, the JPEG first uses HTTP so Flask can serve it later. For a dashboard sample/upload in Webots mode, input metadata reaches the Webots edge over MQTT. In both cases, the inference result uses the simulated radio/gateway path.

## 9. Vibration inference

The orange Webots node has no accelerometer device or physical dynamics. Its controller generates one synthetic sample per 32 ms Webots basic time step with NumPy seed 2026.

Configuration:

- window: 64 non-overlapping samples
- rate: 31.25 Hz
- duration: approximately 2.05 seconds
- baseline: zero-mean normal noise, standard deviation 0.01
- anomaly: 8 Hz sinusoid, amplitude 0.55
- automatic anomaly: every fourth window
- manual trigger: `V` in the focused Edge-2 Webots view

The controller subtracts each completed window's mean before inference.

`TinyVibrationCNN` is:

```text
Conv1d(1, 8, kernel=5, padding=2)
ReLU
MaxPool1d(2)
Conv1d(8, 16, kernel=3, padding=1)
ReLU
AdaptiveAvgPool1d(1)
Linear(16, 2)
```

It has 482 trainable parameters and predicts `normal` or `vibration_anomaly`. PyTorch uses one CPU thread in this controller. The resource profile describes a 512 MB, 2 W low-power target, but does not constrain the laptop.

`vibration/train_model.py` reproducibly creates 600 generated examples per class with seed 20261122, trains for 80 full-batch epochs, saves the state dictionary, and records metadata. Its reported training accuracy is evaluated on those same generated training examples. There is no independent validation/test set or field-labelled data.

## 10. Vibration payload and cloud handling

`vibration/payload.py` packs this 29-byte little-endian structure:

```text
16-byte UUID
4-byte Unix timestamp
1-byte class index
2-byte confidence x 10,000
2-byte RMS g x 10,000
2-byte peak g x 10,000
2-byte latency milliseconds x 1,000
```

The fixed zone string is deliberately not repeated in those 29 bytes. The decoder restores model, window, rate, edge ID, resource-profile metadata, and `zone: north-gate` from shared device configuration after the network server reconstructs the application bytes. The application server persists that zone in `vibration_events`, and the dashboard shows it beside the sensor result.

The cloud stores each new vibration `event_id`. Classification `vibration_anomaly` sets `alert=true` and is published to `perimeter/alerts`. Duplicate IDs are ignored.

## 11. Simulated radio framing

`gateway/radio.py` implements a local LoRaWAN 1.0-style unconfirmed ABP uplink. It is deliberately limited to the application demonstration.

### 11.1 Frame properties

- MHDR byte: `0x40`
- separate four-byte device addresses
- FCtrl byte: zero
- low 16 bits of the uplink counter in the frame
- FPort: 1
- AES-encrypted fragment payload
- four-byte AES-CMAC MIC
- maximum complete Webots packet: 64 bytes

Application data is split into 43-byte chunks. Each plaintext fragment adds an eight-byte local header containing the first counter, fragment index, and fragment count. Up to 256 fragments are accepted.

LoRaWAN-style payload encryption uses the application session key, device address, and full counter. MIC calculation uses the network session key. The decoder verifies device/header, length, port, counter gap, MIC, fragment order, and reassembly identity.

Counters start at zero for each controller run. Replayed frames and jumps larger than 16,384 are rejected. Fresh per-launch keys and fresh decoder state are why the complete launcher should be restarted after resetting Webots.

### 11.2 Transport path

- Camera controller sends on Webots radio channel 40.
- Vibration controller sends on channel 41.
- The gateway has one receiver for each channel.
- The gateway sends the received byte sequence unchanged to UDP port 16803.
- `gateway.network_server` selects a decoder by device address.
- Camera JSON is reassembled directly; vibration bytes pass through the 29-byte codec.
- The reconstructed event is published to the appropriate MQTT edge-result topic.

The camera JSON can require several frames. The vibration payload fits in one.

For presentation evidence, edge controllers print a readable application summary and payload size before transmission. The gateway prints the device address, frame counter, frame size and periodic forwarding progress rather than one noisy line per camera fragment. The network server prints the decoded application summary and total fragment count immediately before MQTT publication. Session keys and decrypted full camera JSON are not logged.

### 11.3 Non-implemented radio behavior

The code does not implement or model:

- OTAA or ABP provisioning outside per-process environment variables;
- join procedures, downlinks, acknowledgements, or confirmed data;
- frequency plans, spreading factors, data rates, coding rates, or channels in the RF sense;
- airtime, range, propagation, interference, packet loss, duty cycle, or ADR;
- a physical end device, gateway, or external network server.

The Webots Emitter/Receiver and localhost UDP bridge are simulated transport. The MQTT broker is not the LoRaWAN gateway.

## 12. MQTT implementation

`broker/app.py` starts an `amqtt` broker bound to the configured host/port. Anonymous authentication is enabled. Clients use Paho MQTT with protocol MQTT 3.1.1, QoS 1, and a 30-second keepalive.

| Topic | Producer | Consumer | Purpose |
| --- | --- | --- | --- |
| `perimeter/camera/+/image` | Flask or mock camera | RGB edge service | Camera metadata and image URL |
| `perimeter/edge/+/result` | Default edge or Webots network server | Cloud service | Camera/vibration inference result |
| `perimeter/status/+/state` | Edge and cloud processes | Cloud service/dashboard | Retained status/profile metadata |
| `perimeter/alerts` | Cloud service | Optional external subscriber | Final alert object |
| `perimeter/cloud/<edge-id>/result` | Cloud service | Optional external subscriber | Compact RGB completion object |

In Webots mode, both edge controllers still use MQTT for retained status, and the RGB controller subscribes to camera input events. Only inference results take the simulated radio path before returning to MQTT.

There is no MQTT user authentication, authorization policy, or TLS.

## 13. Flask API

| Method and route | Success behavior |
| --- | --- |
| `GET /` | Render dashboard |
| `GET /api/health` | Return cloud, MQTT, and model readiness fields |
| `GET /api/status` | Return broker, RGB edge, vibration edge, and cloud state |
| `GET /api/images` | Return the nine built-in samples |
| `GET /api/events?limit=N` | Return newest RGB records; limit clamped to 1–50 |
| `GET /api/vibration-events?limit=N` | Return newest vibration records; limit clamped to 1–50 |
| `POST /api/run` | Publish a selected sample; HTTP 202 |
| `POST /api/upload` | Store and publish an uploaded image; HTTP 202 |
| `POST /api/webots/capture` | Store a Webots frame and return its event; HTTP 201 |
| `GET /uploads/<id>` | Serve an in-memory JPEG with `no-store` caching |
| `POST /api/reset` | Delete all event rows and clear uploads |

Both sample and upload input routes return 503 when MQTT is unavailable. Malformed selections/images return 400; oversized image data returns 413.

The development API has no user authentication, CSRF protection, rate limiting, or reset confirmation.

## 14. Persistence

`cloud.app` creates `perimeter_events.db` in the repository root.

### 14.1 `events`

Stored fields include:

- unique event ID and receive time;
- image name, URL, and source;
- edge summary and JSON detections;
- final summary and JSON detections;
- execution location and decision reason;
- edge and cloud latency;
- alert flag;
- JSON sensor readings;
- Base64 annotated JPEG.

At initialization, code migrates an older table containing `expected_label` into the current answer-free schema if encountered. It also adds `sensor_readings` to an older compatible table when necessary.

### 14.2 `vibration_events`

Stored fields include event/edge IDs, receive time, class, confidence, RMS, peak, latency, model name, parameter count, rate, window size, JSON resource profile, and alert flag.

### 14.3 Durability rules

Built-in sample records can remain across restarts. Browser and Webots images exist only in memory and use source `upload`; their event rows are deleted during cloud initialization because the corresponding URLs no longer exist.

The database is generated application state. It is not source data, a labelled dataset, or accuracy evidence.

## 15. Browser behavior

`cloud/static/app.js` performs no ML. It:

- retrieves the sample list;
- sends sample/upload requests;
- polls component status every 3 seconds;
- polls camera and vibration events every 2 seconds;
- renders server-provided summaries and detections;
- displays the Base64 image already annotated by the cloud;
- derives visible log lines from stored event records;
- and calls `POST /api/reset` from the clear button.

These polling GET requests do not publish MQTT messages or invoke models. Closing the tab stops browser polling while backend services remain active.

## 16. Source map

| File | Responsibility |
| --- | --- |
| `run_demo.py` | Process startup, model checks, readiness, session keys, monitoring, cleanup |
| `config.py` | Shared IDs, paths, ports, topics, profiles, samples, security classes |
| `broker/app.py` | Embedded MQTT broker |
| `edge/app.py` | YOLO11n, summaries, offloading, logical edge service |
| `cloud/app.py` | Flask, YOLO11m, annotation, MQTT handling, alerts, SQLite |
| `sensor/mock_sensor.py` | Direct MQTT sample publisher |
| `gateway/radio.py` | Encryption, MIC, counters, fragmentation, reassembly |
| `gateway/network_server.py` | UDP reception, device decoding, MQTT publication |
| `vibration/model.py` | 482-parameter CNN |
| `vibration/payload.py` | 29-byte binary result codec |
| `vibration/train_model.py` | Reproducible generated-signal training |
| `webots/worlds/edge1_camera_jetson.wbt` | Edge-1 camera/Jetson-profile scene |
| `webots/worlds/edge2_vibration_device.wbt` | Edge-2 simple vibration-device scene |
| `webots/controllers/camera_edge/` | Edge-1 camera, YOLO11n and uplink |
| `webots/controllers/vibration_edge/` | Synthetic sensor, CNN, and uplink |
| `webots/controllers/perimeter_gateway/` | Reusable radio-to-UDP relay for both worlds |
| `webots/controllers/scene_labels/` | World-specific legends and controls |
| `cloud/templates/index.html` | Dashboard markup |
| `cloud/static/app.js` | HTTP actions, polling, rendering |
| `tests/test_models.py` | Assets, inputs, policy, profile, vibration model checks |
| `tests/test_uplink.py` | Radio and compact-payload checks |

## 17. Validation coverage

Run:

```powershell
.\myenv\Scripts\python.exe -B -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m pip check
node --check cloud\static\app.js
```

The 14 Python tests verify:

- YOLO checkpoint and sample-image presence;
- separate Edge-1 and Edge-2 Webots world assignments;
- no answer tag in sample or upload events;
- security summary and offloading behavior;
- topic helpers;
- explicit simulated Jetson/profile metadata;
- vibration checkpoint shape and sub-1,000 parameter size;
- independent camera/vibration addresses and keys;
- multi-frame JSON round trip;
- maximum 64-byte radio frames;
- compact single-frame vibration payload;
- tamper rejection, missing-fragment behavior, and replay rejection.

The unit tests do not execute a full YOLO prediction, launch services, open Webots, measure accuracy, or validate physical performance. An end-to-end Webots check should confirm `[edge]`, `[vibration-edge]`, `[network]`, and `[cloud]` messages and dashboard records.

## 18. Current limitations

The project does not currently provide:

- Jetson, ARM, CUDA, TensorRT, or target GPU execution;
- real camera, accelerometer, or vibration hardware;
- physical LoRa radios or measured network behavior;
- a complete standards-compliant LoRaWAN network;
- ground-truth site labels or field accuracy evaluation;
- measured power, energy, temperature, carbon intensity, or SCI;
- a learned, SLA-aware, or carbon-aware offloading policy;
- durable uploaded-image storage;
- MQTT/HTTP authentication, TLS, authorization, user accounts, or production hosting.

The YOLO checkpoints are pretrained COCO models, but COCO metrics are not accuracy at the intended site. The vibration model's generated-data training score is not field accuracy. The dashboard samples are demonstrations, not an evaluation dataset.

## 19. Physical-deployment direction

A physical implementation should:

1. export and benchmark YOLO11n with TensorRT on the target Jetson;
2. select a CUDA/TensorRT runtime and measure end-to-end latency on that device;
3. acquire synchronized real camera and vibration data with independent labels;
4. use a real LoRaWAN end device, gateway, network server, and regional settings for compact results;
5. send selected images over Wi-Fi, Ethernet, cellular, or another IP-capable path;
6. add authenticated, encrypted service communication and production hosting;
7. measure energy and carbon inputs on actual hardware before reporting SCI or carbon-aware behavior.
