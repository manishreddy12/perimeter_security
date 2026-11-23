# Project notes

The consolidated implementation reference is available in [IMPLEMENTATION.md](IMPLEMENTATION.md).

## What the demonstration proves

The application performs actual neural-network object detection on RGB images. YOLO11n always runs first as the simulated edge model. A confidence/risk rule either accepts that result or asks the laptop to run the larger YOLO11m model.

The default mode simulates the execution flow. The optional Webots mode also supplies simulated camera, GPS, and radio devices. Both models currently use the laptop CPU. The words `edge` and `cloud` describe logical locations implemented as separate MQTT services.

Webots mode also includes a second fixed low-power edge device with a reproducible synthetic vibration input and a 482-parameter 1D CNN. The box has no physical dynamics and cannot slide or fall. It classifies non-overlapping 64-sample windows as `normal` or `vibration_anomaly`. Every fourth window includes an automatic demonstration disturbance, and pressing `V` injects one manually. The model was trained from synthetic waveforms and demonstrates inference flow rather than physical-site accuracy.

Resource profiles are 4 GB and 10 W for the simulated Jetson Nano camera edge, and 512 MB and 2 W for the vibration edge. The profiles are metadata and do not constrain or reserve laptop resources.

## Event flow

```text
Dashboard or mock camera
    -> perimeter/camera/<camera-id>/image
    -> YOLO11n edge worker
    -> perimeter/edge/<edge-id>/result
    -> YOLO11m laptop worker when selected
    -> database, annotated image, alert, and dashboard log
```

The edge accepts confident `normal` and `animal` results. It requests cloud verification when it detects a person, detects a vehicle, or has low-confidence security detections.

An object detector only identifies a person; it cannot know whether the person is authorised. In this demo, a person or vehicle inside the fixed `north-gate` restricted zone is treated as an alert.

## Complete activity when Run detection is pressed

The original `POST /api/run` request does **not** wait for inference and return the final detection. It returns `202 Queued` after publishing the MQTT event. The completed result appears later when the browser polls the event API.

```text
Browser
  | 1. POST /api/run with only a sample key
  v
cloud/app.py Flask route
  | 2. Create camera metadata and image URL
  | 3. Publish MQTT camera event
  | 4. Immediately return HTTP 202 Queued
  v
MQTT broker: perimeter/camera/<camera-id>/image
  |
  v
edge/app.py
  | 5. Download image from image_url
  | 6. Run YOLO11n at 416 px
  | 7. Apply the offloading rule
  | 8. Publish detections and decision
  v
MQTT broker: perimeter/edge/<edge-id>/result
  |
  v
cloud/app.py MQTT handler
  | 9a. If selected_location=cloud, run YOLO11m at 640 px
  | 9b. If selected_location=edge, accept YOLO11n detections
  | 10. Draw boxes, store SQLite event, publish alert if required
  v
perimeter_events.db
  ^
  | 11. Browser later calls GET /api/events
  |
Dashboard displays completed result
```

The exact activities are:

| Step | Activity | Communication | File and function |
| ---: | --- | --- | --- |
| 1 | User presses `Run detection` | Browser JavaScript | `cloud/static/app.js` → `runImage()` |
| 2 | Browser sends the selected neutral sample key | HTTP `POST /api/run` | `cloud/app.py` → `run_image()` |
| 3 | Cloud API creates `event_id`, timestamp, camera ID, zone, filename, URL and source | Local Python | `cloud/app.py` → `run_image()` |
| 4 | Camera metadata is published | MQTT `perimeter/camera/rgb-camera-01/image` | `cloud/app.py` |
| 5 | Broker forwards the message; it performs no ML | MQTT | `broker/app.py` |
| 6 | Edge reads JSON and downloads the RGB image from `image_url` | MQTT metadata + HTTP image GET | `edge/app.py` → `on_message()` and `load_image()` |
| 7 | Edge runs `yolo11n.pt`, extracts boxes/classes/confidences and summarizes the event | Local inference | `edge/app.py` → `EdgeVisionModel.predict()` |
| 8 | Edge selects `edge` or `cloud` | Local rule | `edge/app.py` → `choose_location()` |
| 9 | Edge result and decision are published | MQTT `perimeter/edge/simulated-edge-01/result` | `edge/app.py` |
| 10 | Cloud receives the edge result | MQTT callback | `cloud/app.py` → `on_mqtt_message()` |
| 11 | Cloud optionally runs `yolo11m.pt`, or accepts the edge detections | Local inference/control | `cloud/app.py` → `process_edge_result()` |
| 12 | OpenCV draws boxes from the selected model's coordinates | Local image processing | `cloud/app.py` → `annotate()` |
| 13 | Result, latency, reason, boxes and annotated JPEG are stored | SQLite | `cloud/app.py` → `insert_event()` |
| 14 | Browser reads and displays the completed record | HTTP `GET /api/events` | `cloud/static/app.js` → `refreshEvents()` |

### Exactly what runs at the edge

`edge/app.py` always runs first for every valid camera event:

1. Download and decode the image.
2. Run YOLO11n using a 416-pixel input and confidence threshold `0.25`.
3. Retain only configured person, vehicle and animal COCO classes.
4. Produce class names, confidence values and `[x1, y1, x2, y2]` bounding-box coordinates.
5. Summarize the event as `normal`, `animal`, `person`, or `vehicle`.
6. Select the execution location.

The current offloading rule is:

| Edge result | Selected location |
| --- | --- |
| Person | Cloud |
| Vehicle | Cloud |
| Relevant detections whose maximum confidence is below `0.50` | Cloud |
| Confident animal | Edge |
| No configured security object | Edge |

This is a hand-written risk/confidence rule, not an ML or SCI-based offloading model.

### Exactly what runs in the cloud

The cloud service always receives the edge result because it owns event storage, alerts, annotation and the dashboard API. However, YOLO11m runs only when the edge selected `cloud`.

- For `selected_location=cloud`, the cloud downloads the image again, runs YOLO11m at 640 pixels, and uses the YOLO11m boxes as the final detections.
- For `selected_location=edge`, YOLO11m does not run. The cloud accepts the YOLO11n boxes and only draws/stores them.
- A final person or vehicle result creates an alert. An animal currently does not create an alert.
- The cloud publishes a compact completion result to `perimeter/cloud/<edge-id>/result` and publishes alerts to `perimeter/alerts`.

YOLO calculates the bounding-box coordinates. OpenCV in `cloud/app.py::annotate()` draws the rectangles and labels on a JPEG. The browser does not draw boxes; it displays the already annotated Base64 JPEG returned by `/api/events`.

## Other input and request paths

### Browser upload path

`POST /api/upload` initially carries the actual image bytes over HTTP. `cloud/app.py::upload_image()` validates the file, resizes it when necessary, converts it to JPEG, keeps it temporarily in memory, creates an HTTP image URL, and publishes only that URL plus metadata through MQTT. From that point onward, it follows the same edge and cloud path shown above. No class answer is requested from the user.

### Command-line mock sensor path

`sensor/mock_sensor.py` creates the camera metadata and publishes it directly to `perimeter/camera/<camera-id>/image`. It bypasses `/api/run`; the MQTT broker, edge worker and cloud processing remain the same.

### Dashboard polling path

The browser calls `GET /api/status` every 3 seconds and `GET /api/events` every 2 seconds. These requests do not publish camera events and do not run either YOLO model. They only refresh service health and read completed SQLite records. Because the 2-second and 3-second timers interleave, Flask request logs may appear approximately every second while the dashboard tab is open.

`run_demo.py` also polls `/api/health` and `/api/status` briefly during startup. It stops polling after the edge reports online.

## MQTT messages

The camera event contains:

```json
{
  "event_id": "uuid",
  "camera_id": "rgb-camera-01",
  "zone": "north-gate",
  "image_name": "Sample 03",
  "image_url": "http://127.0.0.1:8000/static/demo_person.jpg",
  "source": "sample"
}
```

For a browser upload, `source` is `upload`, `image_name` is the sanitized filename, and `image_url` points to a temporary in-memory image route. No preset class or user-entered object tag is included.

The edge result adds:

```json
{
  "edge_result": {
    "model": "YOLO11n",
    "summary": "person",
    "latency_ms": 140.2,
    "detections": [
      {"class": "person", "confidence": 0.91, "bbox": [20, 40, 220, 470]}
    ]
  },
  "offload": {
    "selected_location": "cloud",
    "reason": "person is security-sensitive and needs stronger verification"
  }
}
```

Raw JPEG bytes and continuous video are intentionally absent from MQTT.

## Models and images

- `yolo11n.pt`: approximately 2.6 million parameters; used at the edge with 416-pixel input.
- `yolo11m.pt`: approximately 20.1 million parameters; used on the laptop with 640-pixel input.
- `demo_normal.jpg`: COCO8 image `000000000030.jpg`.
- `demo_animal.jpg`: COCO8 image `000000000025.jpg`.
- `demo_person.jpg`: COCO8 image `000000000036.jpg`.
- `demo_vehicle.jpg`: standard Ultralytics `bus.jpg` example.
- `demo_coco_009.jpg`, `demo_coco_034.jpg`, `demo_coco_042.jpg`, `demo_coco_049.jpg`, and `demo_coco_061.jpg`: the other five COCO8 sample images.

The pretrained COCO model classes used by the security rule are:

- person;
- car, motorcycle, bus, and truck;
- bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, and giraffe.

## Repository layout

```text
perimeter_security_demo/
|-- run_demo.py
|-- config.py
|-- yolo11n.pt
|-- yolo11m.pt
|-- broker/app.py
|-- edge/app.py
|-- cloud/app.py
|-- sensor/mock_sensor.py
|-- cloud/templates/index.html
|-- cloud/static/               # CSS, JavaScript, and nine RGB images
|-- docs/README.md
`-- tests/test_models.py
```

The old synthetic sensor generator, hand-built logistic regression, small MLP, training script, and separate model/database helper files were removed. Their temperature values were artificial and are not used by this RGB version.

## Which file contains the application?

The current RGB system is a small service-based application, so it is intentionally not contained in one `app.py` file.

| File | Responsibility |
| --- | --- |
| `run_demo.py` | Main terminal entry point. Starts the broker, cloud and edge processes and waits for readiness. |
| `config.py` | Shared ports, MQTT topics, model paths, sample-image list and security classes. |
| `broker/app.py` | Local MQTT 3.1.1 broker. It routes messages and performs no inference. |
| `edge/app.py` | YOLO11n inference, detection filtering, event summary and offloading decision. |
| `cloud/app.py` | Flask API, browser uploads, MQTT result handler, optional YOLO11m inference, annotation, alerts and SQLite storage. |
| `cloud/templates/index.html` | Dashboard HTML structure. |
| `cloud/static/app.js` | Button/upload actions, HTTP requests, polling and result rendering. It performs no ML. |
| `cloud/static/style.css` | Dashboard styling. |
| `sensor/mock_sensor.py` | Optional terminal-based camera-event publisher. |
| `tests/test_models.py` | Checks model files, images, topics, offloading and answer-free upload/sample events. |

Therefore, the command to start the **current RGB application** is `python run_demo.py`. `perimeter_security_previous_demo/app.py` belongs to the separate older 5×4 sensor-matrix prototype; it is not used by this application.

## Starting and presenting the demo

In PowerShell, start the complete application with:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security_demo
.\myenv\Scripts\python.exe run_demo.py
```

Then present it as follows:

1. Wait until the terminal prints `RGB object-detection demo is running`.
2. Open http://127.0.0.1:8000.
3. Run two or three neutral samples and show the model-generated detections.
4. Drop your own image into the upload box and show that no class input is requested.
5. Point out the two different models, bounding boxes, MQTT decision, final location, and alert log.
6. Return to PowerShell and press `Ctrl+C` to stop all three services.

The first inference may be slower because PyTorch initializes its CPU kernels.

## LoRaWAN relationship

LoRaWAN cannot reasonably transport RGB images. The later physical design should be:

```text
camera -> Jetson edge detection -> compact LoRaWAN detection -> network server -> MQTT
```

If the cloud must rerun object detection, the selected image should travel through Wi-Fi, Ethernet, or cellular HTTP. LoRaWAN can carry the alert and an image identifier.

## Moving to a real Jetson

1. Copy `edge/app.py`, `config.py`, and `yolo11n.pt` to the Jetson.
2. Export YOLO11n to TensorRT on that Jetson.
3. Change the edge model loader to use the TensorRT engine.
4. Point the Jetson MQTT client at the laptop broker IP.
5. Replace the demo image URL with frames from a real RGB camera.
6. Measure actual latency and power before adding SCI calculations.

## Troubleshooting

- If port 1883 or 8000 is busy, close the earlier demo terminal.
- If the page says `WAITING FOR EDGE`, read the edge console for model or image-download errors.
- If packages are missing, run `.\myenv\Scripts\python.exe -m pip install -r requirements.txt`.
- If an image produces no relevant box, remember that only person, vehicle, and animal COCO classes are retained.
- Browser uploads support JPG, PNG, and WebP files up to 8 MB and are removed from memory when the application stops.

## Webots mode

See the root README for the Webots startup command and uplink flow. Webots identifies the edge controller as a simulated NVIDIA Jetson Nano with a 4 GB, 10 W profile. YOLO11n still executes on the Windows laptop CPU, so measured latency is laptop latency. The application server continues to handle annotation, alerts, SQLite, and conditional YOLO11m inference.
