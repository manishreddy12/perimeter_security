from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests
from flask import Flask, Response, jsonify, render_template, request, url_for
from ultralytics import YOLO
from werkzeug.utils import secure_filename

from config import (
    ALERT_TOPIC,
    ANIMAL_CLASSES,
    CLOUD_HOST,
    CLOUD_MODEL_PATH,
    CLOUD_PORT,
    DATABASE_PATH,
    DEMO_IMAGES,
    EDGE_ID,
    EDGE_RESULT_TOPIC,
    MQTT_HOST,
    MQTT_KEEPALIVE,
    MQTT_PORT,
    MQTT_QOS,
    PERIMETER_ZONE,
    PERSON_CLASSES,
    SECURITY_CLASSES,
    STATUS_TOPIC,
    VEHICLE_CLASSES,
    VIBRATION_EDGE_ID,
    sensor_topic,
    status_topic,
)


MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_STORED_UPLOADS = 20

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
mqtt_client: mqtt.Client | None = None
cloud_model: YOLO | None = None
broker_connected = threading.Event()
status_lock = threading.Lock()
component_status: dict[str, dict[str, Any]] = {}
upload_lock = threading.Lock()
uploaded_images: OrderedDict[str, tuple[bytes, str]] = OrderedDict()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def create_events_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                received_at TEXT NOT NULL,
                image_name TEXT NOT NULL,
                image_url TEXT NOT NULL,
                image_source TEXT NOT NULL,
                edge_summary TEXT NOT NULL,
                edge_detections TEXT NOT NULL,
                final_summary TEXT NOT NULL,
                final_detections TEXT NOT NULL,
                execution_location TEXT NOT NULL,
                reason TEXT NOT NULL,
                edge_latency_ms REAL NOT NULL,
                cloud_latency_ms REAL NOT NULL,
                alert INTEGER NOT NULL,
                sensor_readings TEXT NOT NULL DEFAULT '{}',
                annotated_image TEXT NOT NULL
            )
        """
    )


def create_vibration_events_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vibration_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                received_at TEXT NOT NULL,
                edge_id TEXT NOT NULL,
                zone TEXT NOT NULL,
                classification TEXT NOT NULL,
                confidence REAL NOT NULL,
                rms_g REAL NOT NULL,
                peak_g REAL NOT NULL,
                latency_ms REAL NOT NULL,
                model TEXT NOT NULL,
                model_parameters INTEGER NOT NULL,
                sample_rate_hz REAL NOT NULL,
                window_samples INTEGER NOT NULL,
                resource_profile TEXT NOT NULL,
                alert INTEGER NOT NULL
            )
        """
    )


def initialize_database() -> None:
    with connect_db() as connection:
        create_vibration_events_table(connection)
        vibration_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(vibration_events)").fetchall()
        }
        if vibration_columns and "zone" not in vibration_columns:
            connection.execute(
                "ALTER TABLE vibration_events ADD COLUMN zone TEXT NOT NULL "
                f"DEFAULT '{PERIMETER_ZONE}'"
            )
        columns = {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(events)").fetchall()
        }
        if columns and "expected_label" in columns:
            connection.execute("ALTER TABLE events RENAME TO events_legacy")
            create_events_table(connection)
            connection.execute(
                """
                INSERT INTO events (
                    id, event_id, received_at, image_name, image_url, image_source,
                    edge_summary, edge_detections, final_summary, final_detections,
                    execution_location, reason, edge_latency_ms, cloud_latency_ms,
                    alert, annotated_image
                )
                SELECT
                    id, event_id, received_at, image_name, image_url, 'sample',
                    edge_summary, edge_detections, final_summary, final_detections,
                    execution_location, reason, edge_latency_ms, cloud_latency_ms,
                    alert, annotated_image
                FROM events_legacy
                """
            )
            connection.execute("DROP TABLE events_legacy")
        else:
            create_events_table(connection)
            if columns and "sensor_readings" not in columns:
                connection.execute("ALTER TABLE events ADD COLUMN sensor_readings TEXT NOT NULL DEFAULT '{}'")
        # Browser uploads are intentionally in memory and disappear on restart.
        connection.execute("DELETE FROM events WHERE image_source='upload'")


def insert_event(record: dict[str, Any]) -> None:
    columns = list(record)
    with connect_db() as connection:
        connection.execute(
            f"INSERT OR REPLACE INTO events ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [record[name] for name in columns],
        )


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (max(1, min(limit, 50)),)
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["edge_detections"] = json.loads(event["edge_detections"])
        event["final_detections"] = json.loads(event["final_detections"])
        event["sensor_readings"] = json.loads(event["sensor_readings"])
        event["alert"] = bool(event["alert"])
        events.append(event)
    return events


def insert_vibration_event(payload: dict[str, Any]) -> dict[str, Any]:
    classification = str(payload["classification"])
    record = {
        "event_id": str(payload["event_id"]),
        "received_at": now_iso(),
        "edge_id": str(payload["edge_id"]),
        "zone": str(payload.get("zone", PERIMETER_ZONE)),
        "classification": classification,
        "confidence": float(payload["confidence"]),
        "rms_g": float(payload["rms_g"]),
        "peak_g": float(payload["peak_g"]),
        "latency_ms": float(payload["latency_ms"]),
        "model": str(payload["model"]),
        "model_parameters": int(payload["model_parameters"]),
        "sample_rate_hz": float(payload["sample_rate_hz"]),
        "window_samples": int(payload["window_samples"]),
        "resource_profile": json.dumps(payload["resource_profile"]),
        "alert": int(classification == "vibration_anomaly"),
    }
    columns = list(record)
    with connect_db() as connection:
        connection.execute(
            f"INSERT OR REPLACE INTO vibration_events ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [record[name] for name in columns],
        )
    return {**record, "resource_profile": payload["resource_profile"], "alert": bool(record["alert"])}


def recent_vibration_events(limit: int = 20) -> list[dict[str, Any]]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT * FROM vibration_events ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 50)),),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["resource_profile"] = json.loads(event["resource_profile"])
        event["alert"] = bool(event["alert"])
        events.append(event)
    return events


def load_image(image_url: str) -> np.ndarray:
    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    image = cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not decode image from {image_url}")
    return image


def security_detections(result) -> list[dict[str, object]]:
    detections: list[dict[str, object]] = []
    if result.boxes is None:
        return detections
    for box in result.boxes:
        class_name = str(result.names[int(box.cls.item())])
        if class_name in SECURITY_CLASSES:
            detections.append(
                {
                    "class": class_name,
                    "confidence": round(float(box.conf.item()), 4),
                    "bbox": [round(float(value), 1) for value in box.xyxy[0].tolist()],
                }
            )
    return detections


def summarize(detections: list[dict[str, object]]) -> str:
    classes = {str(item["class"]) for item in detections}
    if classes & VEHICLE_CLASSES:
        return "vehicle"
    if classes & PERSON_CLASSES:
        return "person"
    if classes & ANIMAL_CLASSES:
        return "animal"
    return "normal"


def annotate(image: np.ndarray, detections: list[dict[str, object]], model_name: str) -> str:
    colors = {"person": (60, 60, 230), "vehicle": (20, 150, 245), "animal": (70, 180, 70)}
    for detection in detections:
        class_name = str(detection["class"])
        group = "person" if class_name in PERSON_CLASSES else "vehicle" if class_name in VEHICLE_CLASSES else "animal"
        color = colors[group]
        x1, y1, x2, y2 = [int(value) for value in detection["bbox"]]
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
        label = f"{class_name} {float(detection['confidence']):.0%}"
        cv2.putText(image, label, (x1, max(25, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.putText(image, model_name, (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise RuntimeError("Could not encode annotated image")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def run_cloud_inference(image_url: str) -> tuple[list[dict[str, object]], float, str]:
    if cloud_model is None:
        raise RuntimeError("Cloud model is not loaded")
    image = load_image(image_url)
    started = time.perf_counter()
    result = cloud_model.predict(image, imgsz=640, conf=0.25, device="cpu", verbose=False)[0]
    latency_ms = (time.perf_counter() - started) * 1000.0
    detections = security_detections(result)
    return detections, round(latency_ms, 2), annotate(image, detections, "Cloud YOLO11m")


def process_edge_result(payload: dict[str, Any]) -> dict[str, Any]:
    camera_event = payload["camera_event"]
    edge_result = payload["edge_result"]
    selected = payload["offload"]["selected_location"]
    edge_detections = list(edge_result["detections"])
    if selected == "cloud":
        final_detections, cloud_latency, annotated_image = run_cloud_inference(camera_event["image_url"])
        final_summary = summarize(final_detections)
    else:
        image = load_image(camera_event["image_url"])
        final_detections = edge_detections
        cloud_latency = 0.0
        final_summary = str(edge_result["summary"])
        annotated_image = annotate(image, final_detections, "Edge YOLO11n")

    alert = final_summary in {"person", "vehicle"}
    record = {
        "event_id": str(payload["event_id"]),
        "received_at": now_iso(),
        "image_name": str(camera_event["image_name"]),
        "image_url": str(camera_event["image_url"]),
        "image_source": str(camera_event.get("source", "camera")),
        "sensor_readings": json.dumps(camera_event.get("sensor_readings", {})),
        "edge_summary": str(edge_result["summary"]),
        "edge_detections": json.dumps(edge_detections),
        "final_summary": final_summary,
        "final_detections": json.dumps(final_detections),
        "execution_location": selected,
        "reason": str(payload["offload"]["reason"]),
        "edge_latency_ms": float(edge_result["latency_ms"]),
        "cloud_latency_ms": cloud_latency,
        "alert": int(alert),
        "annotated_image": annotated_image,
    }
    insert_event(record)
    return {
        "event_id": record["event_id"],
        "final_summary": final_summary,
        "execution_location": selected,
        "alert": alert,
    }


def cloud_status(state: str) -> dict[str, object]:
    return {
        "status": state,
        "component": "cloud",
        "model": "YOLO11m",
        "runtime": "laptop CPU",
        "timestamp": now_iso(),
    }


def on_mqtt_connect(client, userdata, flags, reason_code, properties) -> None:
    if reason_code == 0:
        broker_connected.set()
        client.subscribe(EDGE_RESULT_TOPIC, qos=MQTT_QOS)
        client.subscribe(STATUS_TOPIC, qos=MQTT_QOS)
        client.publish(status_topic("cloud-laptop"), json.dumps(cloud_status("online")), qos=MQTT_QOS, retain=True)
        print(f"[cloud] YOLO11m subscribed to {EDGE_RESULT_TOPIC}", flush=True)


def on_mqtt_disconnect(client, userdata, disconnect_flags, reason_code, properties) -> None:
    broker_connected.clear()


def on_mqtt_message(client, userdata, message) -> None:
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        if message.topic.startswith("perimeter/status/"):
            with status_lock:
                component_status[message.topic.split("/")[2]] = payload
            return
        event_id = str(payload.get("event_id", ""))
        if payload.get("event_type") == "vibration":
            with connect_db() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM vibration_events WHERE event_id=?", (event_id,)
                ).fetchone()
            if exists:
                return
            result = insert_vibration_event(payload)
            if result["alert"]:
                client.publish(ALERT_TOPIC, json.dumps(result), qos=MQTT_QOS)
            print(
                f"[cloud] vibration {event_id[:8]} -> {result['classification']} "
                f"({result['confidence']:.0%})",
                flush=True,
            )
            return
        with connect_db() as connection:
            if connection.execute("SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone():
                return
        result = process_edge_result(payload)
        client.publish(f"perimeter/cloud/{EDGE_ID}/result", json.dumps(result), qos=MQTT_QOS)
        if result["alert"]:
            client.publish(ALERT_TOPIC, json.dumps(result), qos=MQTT_QOS)
        print(
            f"[cloud] {event_id[:8]} -> {result['execution_location']} -> "
            f"{result['final_summary']}{' ALERT' if result['alert'] else ''}",
            flush=True,
        )
    except Exception as exc:
        print(f"[cloud] failed to process edge result: {exc}", flush=True)


def start_mqtt() -> None:
    global mqtt_client
    mqtt_client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="perimeter-cloud-laptop",
        protocol=mqtt.MQTTv311,
    )
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
    mqtt_client.loop_start()
    if not broker_connected.wait(10):
        raise RuntimeError("Cloud could not connect to the MQTT broker")


@app.get("/")
def dashboard():
    return render_template("index.html")


@app.errorhandler(413)
def upload_too_large(error):
    return jsonify({"error": "Image is too large. Maximum upload size is 8 MB."}), 413


@app.get("/uploads/<upload_id>")
def serve_uploaded_image(upload_id: str):
    with upload_lock:
        stored = uploaded_images.get(upload_id)
    if stored is None:
        return jsonify({"error": "Uploaded image is no longer available"}), 404
    image_bytes, _ = stored
    return Response(
        image_bytes,
        mimetype="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "mqtt": broker_connected.is_set(), "model": "YOLO11m"})


@app.get("/api/status")
def status():
    with status_lock:
        edge = component_status.get(EDGE_ID, {"status": "unreachable", "model": "YOLO11n"})
        vibration_edge = component_status.get(
            VIBRATION_EDGE_ID,
            {"status": "unreachable", "model": "Tiny 1D CNN"},
        )
    return jsonify(
        {
            "mqtt_broker": {"status": "ok" if broker_connected.is_set() else "unreachable"},
            "edge": edge,
            "vibration_edge": vibration_edge,
            "cloud": cloud_status("online"),
        }
    )


@app.get("/api/images")
def images():
    items = []
    for key, details in DEMO_IMAGES.items():
        items.append({"key": key, **details, "url": url_for("static", filename=details["file"])})
    return jsonify({"images": items})


@app.get("/api/events")
def events():
    try:
        limit = int(request.args.get("limit", "12"))
    except ValueError:
        limit = 12
    return jsonify({"events": recent_events(limit)})


@app.get("/api/vibration-events")
def vibration_events():
    try:
        limit = int(request.args.get("limit", "12"))
    except ValueError:
        limit = 12
    return jsonify({"events": recent_vibration_events(limit)})


@app.post("/api/run")
def run_image():
    if mqtt_client is None or not broker_connected.is_set():
        return jsonify({"error": "MQTT broker is unavailable"}), 503
    body = request.get_json(silent=True) or {}
    image_key = str(body.get("image", ""))
    if image_key not in DEMO_IMAGES:
        return jsonify({"error": "Choose one of the provided demonstration images"}), 400
    details = DEMO_IMAGES[image_key]
    relative_url = url_for("static", filename=details["file"])
    camera_event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": now_iso(),
        "camera_id": "rgb-camera-01",
        "zone": PERIMETER_ZONE,
        "image_name": details["title"],
        "image_url": request.host_url.rstrip("/") + relative_url,
        "source": "sample",
    }
    info = mqtt_client.publish(sensor_topic("rgb-camera-01"), json.dumps(camera_event), qos=MQTT_QOS)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        return jsonify({"error": "Could not publish the image event"}), 503
    return jsonify({"queued": True, "event_id": camera_event["event_id"]}), 202


@app.post("/api/upload")
def upload_image():
    return store_image("browser-upload")


@app.post("/api/webots/capture")
def webots_capture():
    return store_image("webots-camera")


def store_image(camera_id: str):
    if mqtt_client is None or not broker_connected.is_set():
        return jsonify({"error": "MQTT broker is unavailable"}), 503
    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Choose a JPG, PNG, or WebP image"}), 400

    raw_bytes = uploaded.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "Image is too large. Maximum upload size is 8 MB."}), 413
    image = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return jsonify({"error": "The selected file is not a readable image"}), 400

    height, width = image.shape[:2]
    largest_side = max(height, width)
    if largest_side > 1600:
        scale = 1600.0 / largest_side
        image = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        return jsonify({"error": "Could not prepare the image for inference"}), 400

    upload_id = uuid.uuid4().hex
    display_name = secure_filename(uploaded.filename)[:100] or "uploaded-image.jpg"
    with upload_lock:
        uploaded_images[upload_id] = (encoded.tobytes(), display_name)
        while len(uploaded_images) > MAX_STORED_UPLOADS:
            uploaded_images.popitem(last=False)

    relative_url = url_for("serve_uploaded_image", upload_id=upload_id)
    camera_event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": now_iso(),
        "camera_id": camera_id,
        "zone": PERIMETER_ZONE,
        "image_name": display_name,
        "image_url": request.host_url.rstrip("/") + relative_url,
        "source": "upload",
    }
    if camera_id == "webots-camera":
        return jsonify(camera_event), 201
    info = mqtt_client.publish(
        sensor_topic(camera_id), json.dumps(camera_event), qos=MQTT_QOS
    )
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        with upload_lock:
            uploaded_images.pop(upload_id, None)
        return jsonify({"error": "Could not publish the uploaded image event"}), 503
    return jsonify(
        {
            "queued": True,
            "event_id": camera_event["event_id"],
            "image_name": display_name,
        }
    ), 202


@app.post("/api/reset")
def reset():
    with connect_db() as connection:
        connection.execute("DELETE FROM events")
        connection.execute("DELETE FROM vibration_events")
    with upload_lock:
        uploaded_images.clear()
    return jsonify({"status": "cleared"})


def main() -> None:
    global cloud_model
    initialize_database()
    print(f"[cloud] loading YOLO11m from {CLOUD_MODEL_PATH.name}", flush=True)
    cloud_model = YOLO(str(CLOUD_MODEL_PATH))
    start_mqtt()
    app.run(host=CLOUD_HOST, port=CLOUD_PORT, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
