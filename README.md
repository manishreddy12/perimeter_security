# RGB Edge-and-Cloud Perimeter Demo

This project demonstrates camera and vibration inference across two simulated edge devices and a laptop application server.

For a code-grounded description of the running components, communication paths, models, APIs, storage, and limitations, see [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).

```text
RGB demo image
    -> MQTT image event
    -> simulated edge: YOLO11n
    -> MQTT detections and offload decision
    -> laptop cloud: YOLO11m when verification is required
    -> SQLite event log and dashboard
```

## Run from a terminal

Open PowerShell and run:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security_demo
.\myenv\Scripts\python.exe run_demo.py
```

Wait until the terminal prints `RGB object-detection demo is running`, then open http://127.0.0.1:8000. Keep the terminal open while presenting the demo. Press `Ctrl+C` in that terminal to stop the broker, edge service, and cloud service.

Choose one of the nine neutral sample images, or drag and drop your own JPG, PNG, or WebP image. The page displays the original image, bounding boxes, edge result, final result, execution location, latency, and application logs. No preset class or user-provided object tag is sent to the models.

## Models

| Location | Model | Role |
| --- | --- | --- |
| Simulated edge | YOLO11n, 416-pixel input | Small detector that runs first on every RGB image |
| Vibration edge | Tiny 1D CNN, 64-sample input | Classifies normal and anomalous vibration windows |
| Laptop cloud | YOLO11m, 640-pixel input | Larger detector used for people, vehicles, and uncertain edge results |

Both models use pretrained COCO weights. They detect people, vehicles, and common animals. The edge currently runs on the Windows CPU; it does not emulate Jetson performance. A later Jetson version should export YOLO11n to TensorRT.

## Images

Nine images are stored directly in `cloud/static/` so the demo works offline. Eight come from the official COCO8 sample and one is the standard Ultralytics bus example. They appear as `Sample 01` through `Sample 09`, without content labels.

An uploaded image is validated, resized to at most 1600 pixels on its longest side, converted to JPEG, and held only in memory while the application is running. The upload limit is 8 MB. It follows the same MQTT, edge, offloading, and cloud path as a built-in sample.

## Important communication detail

MQTT carries an image URL, event metadata, bounding boxes, classes, and confidence values. It does not carry the JPEG bytes. In a physical system, LoRaWAN should carry only compact alerts/detections. A selected RGB image would require an IP path such as Wi-Fi, Ethernet, or cellular HTTP.

## Main files

| File | Purpose |
| --- | --- |
| `run_demo.py` | Starts the broker, cloud, and edge processes |
| `config.py` | Ports, MQTT topics, image list, model paths, and security classes |
| `broker/app.py` | Local MQTT broker |
| `edge/app.py` | YOLO11n inference and offloading decision |
| `cloud/app.py` | YOLO11m inference, SQLite, APIs, and dashboard |
| `sensor/mock_sensor.py` | Optional command-line RGB image publisher |
| `cloud/templates/index.html` | Dashboard page |
| `cloud/static/app.js` | Dashboard actions and polling |
| `docs/README.md` | Architecture, MQTT messages, and detailed instructions |

## Manual image publisher

With the demo running:

```powershell
.\myenv\Scripts\python.exe -m sensor.mock_sensor --image sample_03 --count 1
```

Valid image names are `sample_01` through `sample_09`, plus `cycle`.

## First-time installation on another computer

```powershell
cd <path-to-perimeter_security_demo>
python -m venv myenv
.\myenv\Scripts\python.exe -m pip install -r requirements.txt
.\myenv\Scripts\python.exe run_demo.py
```

The local `yolo11n.pt` and `yolo11m.pt` files make this copy usable without downloading weights again.

## Webots mode

From this checkout's root, install [Webots R2025a for Windows](https://github.com/cyberbotics/webots/releases/tag/R2025a), then run:

```powershell
py -3.12 -m venv myenv
.\myenv\Scripts\python.exe -m pip install -r requirements.txt
.\myenv\Scripts\python.exe run_demo.py --webots
```

Set `PERIMETER_WEBOTS_EXE` to the Webots executable if the launcher cannot find it.
Webots starts a simulated NVIDIA Jetson Nano camera edge, a fixed low-power vibration edge, and a gateway. The vibration box has no physical dynamics, so it cannot slide or fall; its controller generates reproducible synthetic sensor samples for the 1D CNN. It captures an initial camera frame automatically. Focus the running 3D view and press **C** to capture another camera frame or **V** to inject vibration into the current sensor window.
The Webots 3D view includes a fixed on-screen legend identifying the green camera edge, orange vibration edge, blue gateway, and brown camera target.
The dashboard at http://127.0.0.1:8000 also accepts the existing samples and uploads for testing with real photographs.
The simple 3D scene can yield a normal result.

YOLO11n runs inside the simulated Jetson Nano camera controller. Computation still executes on the laptop CPU. The profile represents a 4 GB Nano in its 10 W mode and does not emulate ARM, CUDA, TensorRT, temperature, energy use, or Jetson inference speed. The event also carries the stationary node's simulated GPS position in metres, which Flask stores in SQLite. The JPEG travels over local HTTP for storage, annotation, and optional YOLO11m verification.
Both edge devices use distinct addresses and session keys. Their results travel through Webots' simulated radio as encrypted LoRaWAN 1.0 unconfirmed uplink frames.
The gateway relays the frames over UDP port 16803 to the local Python network server.
The network server verifies the MIC and frame counter, reassembles the result, and publishes it over MQTT to the existing Flask application.
Restart the launcher after resetting the Webots world to establish fresh session keys and counters.

The vibration node uses a 512 MB, 2 W target profile and a 482-parameter 1D CNN. The camera node retains its 4 GB, 10 W Jetson Nano profile. These are simulated target requirements and do not reserve laptop RAM. The 1D CNN checkpoint is trained from reproducible synthetic normal and anomalous waveforms, so its synthetic training score is not field accuracy. Retrain it with `.\myenv\Scripts\python.exe -m vibration.train_model`.

This is a two-device ABP uplink demonstration with per-launch session keys and application-specific fragmentation.
RF behavior, airtime, duty cycle, and downlinks are outside the simulation.
Browser requests still use MQTT to deliver input image URLs.
Run without `--webots` for the original MQTT-only demo.

To stop the complete demo, click inside the PowerShell window once and press `Ctrl+C` once. Wait for `Stopping demo...`; additional `Ctrl+C` presses are ignored while the launcher closes Webots and its child services.
