# RGB Edge-and-Cloud Perimeter Demo

This is a small project demonstration of real object detection at two execution locations.

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
