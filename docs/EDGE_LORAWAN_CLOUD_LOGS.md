# Edge, LoRaWAN, MQTT and cloud log evidence

## Purpose

This guide shows how to demonstrate the complete event path in terminal logs. It covers camera and vibration events from edge inference through the simulated LoRaWAN gateway and network server to MQTT and the application server.

Values such as UUIDs, confidence and latency vary on every run. Lines containing placeholders such as `<event-id>` show the expected format.

## Start the full path

In PowerShell:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security-main
.\myenv\Scripts\python.exe run_demo.py --webots
```

Wait for:

```text
[broker] MQTT 3.1.1 listening on 127.0.0.1:1883
[cloud] YOLO11m subscribed to perimeter/edge/+/result
[network] gateway backhaul listening on UDP 16803
[edge] YOLO11n subscribed to perimeter/camera/+/image
[vibration-edge] Tiny 1D CNN ready: 482 parameters, 512 MB profile
RGB object-detection demo is running.
```

These lines establish that the broker, application server, network server and both edge models are ready.

## Meaning of each log prefix

| Prefix | Component | Evidence provided |
| --- | --- | --- |
| `[broker]` | Embedded MQTT broker | MQTT listener is ready |
| `[edge]` | Webots camera edge | YOLO11n result and edge/cloud decision |
| `[vibration-edge]` | Webots vibration edge | CNN class, confidence and inference latency |
| `[lorawan-tx]` | Edge radio encoder | Zone, device address, event, application bytes, and fragment count |
| `[lorawan-payload]` | Edge application | Human-readable fields placed in the uplink; vibration also shows its 29-byte hex form |
| `[gateway]` | Webots gateway relay | Device address, frame counter, frame size, and compact UDP forwarding progress |
| `[lorawan-rx]` | LoRaWAN-style network server | Verified/reassembled application result and total fragments |
| `[network]` | Network-server MQTT bridge | Decoded event and destination MQTT topic |
| `[cloud]` | Application server | MQTT result consumed, stored and optionally alerted/offloaded |
| Flask access line | HTTP API/image server | Image POST/GET and dashboard polling |

Each Webots world has a gateway relay controller. Camera results often require many fragments, so the gateway prints fragment 1 and then progress every 10 frames instead of flooding the terminal. Vibration fits in one frame. A later `[lorawan-rx]` line proves successful verification, decryption, and reassembly; `[network]` shows the MQTT handoff.

## Camera event accepted at the edge

Press `C` in the focused Edge-1 camera view. A typical edge-accepted event produces:

```text
127.0.0.1 - - [...] "POST /api/webots/capture HTTP/1.1" 201 -
[edge] webots-camera.jpg -> normal -> edge (2046 ms)
[lorawan-tx][edge-1] zone=north-gate devaddr=DA1B0126 event=<event> payload=<bytes>B fragments=<count>
[lorawan-payload][edge-1] object=normal confidence=0.0% boxes=0 decision=edge image_ref=HTTP_URL
[gateway][edge-1] forwarded=1 devaddr=DA1B0126 fcnt=<counter> frame=64B -> UDP:16803
[gateway][edge-1] forwarded=10 devaddr=DA1B0126 fcnt=<counter> frame=64B -> UDP:16803
[lorawan-rx][edge-1] zone=north-gate event=<event> fragments=<count> object=normal boxes=0 decision=edge
[network] event=<event> -> MQTT perimeter/edge/simulated-edge-01/result
127.0.0.1 - - [...] "GET /uploads/<upload-id> HTTP/1.1" 200 -
[cloud] <event-prefix> zone=north-gate -> edge -> normal
```

Interpretation:

1. Webots posted the captured JPEG to the HTTP image store.
2. YOLO11n ran and the decision rule accepted the result.
3. The edge summary shows exactly what application data was encoded; `image_ref=HTTP_URL` proves the JPEG bytes were not included.
4. Compact JSON fragments crossed radio channel 40 and the Edge-1 gateway relay.
5. The shared network server reconstructed the stated number of fragments and published the event to MQTT.
6. The application server retrieved the image for annotation, stored the record and logged the final result.

## Camera event offloaded to YOLO11m

The simple Webots scene can produce `normal`. To demonstrate cloud verification reliably, select a person or vehicle sample in the dashboard while Webots mode is running.

Expected pattern:

```text
[edge] Sample 03 -> person -> cloud (<edge-latency> ms)
[lorawan-tx][edge-1] zone=north-gate devaddr=DA1B0126 event=<event> payload=<bytes>B fragments=<count>
[lorawan-payload][edge-1] object=person confidence=<percent> boxes=<count> decision=cloud image_ref=HTTP_URL
[lorawan-rx][edge-1] zone=north-gate event=<event> fragments=<count> object=person boxes=<count> decision=cloud
[network] event=<event> -> MQTT perimeter/edge/simulated-edge-01/result
127.0.0.1 - - [...] "GET /static/demo_person.jpg HTTP/1.1" 200 -
[cloud] <event-prefix> zone=north-gate -> cloud -> person ALERT
```

Interpretation:

- The sample metadata reached the Webots edge through MQTT.
- YOLO11n selected `cloud`.
- The edge result returned through the simulated LoRaWAN gateway and network server.
- The application server consumed it from MQTT, retrieved the image and ran YOLO11m.
- The final result was stored and published as an alert.

Actual final detections can differ because they come from model inference rather than a preset answer.

## Vibration event

Press `V` in the focused Edge-2 vibration view, or wait for every fourth automatic anomaly window.

Typical output:

```text
[vibration-edge] window 4 -> vibration_anomaly (100%, 0.55 ms)
[lorawan-tx][edge-2] zone=north-gate devaddr=DA1B0226 event=<event> payload=29B fragments=1
[lorawan-payload][edge-2] anomaly=YES confidence=100.0% rms=<value>g peak=<value>g compact_hex=<58 hex characters>
[gateway][edge-2] forwarded=1 devaddr=DA1B0226 fcnt=<counter> frame=<bytes>B -> UDP:16803
[lorawan-rx][edge-2] zone=north-gate event=<event> fragments=1 anomaly=YES confidence=100.0% rms=<value>g
[network] event=<event> -> MQTT perimeter/edge/vibration-edge-01/result
[cloud] vibration <event-prefix> zone=north-gate -> vibration_anomaly (100%)
```

Interpretation:

1. The vibration controller completed a 64-sample window and ran the 1D CNN.
2. It encoded the result into the 29-byte application payload.
3. The payload fit in one encrypted radio frame on channel 41.
4. The gateway relayed the frame to UDP 16803.
5. The network server validated and decoded it, then published it to MQTT.
6. The application server stored it and published an alert for `vibration_anomaly`.

## Watch raw MQTT application messages

After the Webots demo is running, open a second PowerShell window:

```powershell
cd D:\IIITB\Sems\20CrdProject\Perimeter_Sec\perimeter_security-main
.\myenv\Scripts\amqtt_sub.exe --url mqtt://127.0.0.1:1883 -q 1 `
  -t "perimeter/edge/+/result" `
  -t "perimeter/cloud/+/result" `
  -t "perimeter/alerts"
```

This displays decoded MQTT application payloads after the network-server boundary. Use `Ctrl+C` to stop only the subscriber.

To observe all project topics, including retained status and camera input metadata:

```powershell
.\myenv\Scripts\amqtt_sub.exe --url mqtt://127.0.0.1:1883 -q 1 -t "perimeter/#"
```

The full subscription is noisy because it includes component status messages.

## Important camera-result fields

In `perimeter/edge/simulated-edge-01/result`:

```json
{
  "event_id": "uuid",
  "camera_event": {
    "zone": "north-gate",
    "image_name": "webots-camera.jpg",
    "image_url": "http://127.0.0.1:8000/uploads/...",
    "source": "upload"
  },
  "edge_result": {
    "summary": "person",
    "detections": [
      {"class": "person", "confidence": 0.91, "bbox": [20, 40, 220, 470]}
    ],
    "latency_ms": 140.2,
    "model": "YOLO11n"
  },
  "offload": {
    "selected_location": "cloud",
    "reason": "person is security-sensitive and needs stronger verification"
  }
}
```

The numbers above illustrate the schema; they are not fixed model output.

## Important vibration fields

After binary decoding, MQTT receives fields including:

```json
{
  "event_type": "vibration",
  "event_id": "uuid",
  "edge_id": "vibration-edge-01",
  "zone": "north-gate",
  "classification": "vibration_anomaly",
  "confidence": 0.998,
  "rms_g": 0.388,
  "peak_g": 0.56,
  "latency_ms": 0.55,
  "model": "Tiny 1D CNN",
  "model_parameters": 482,
  "sample_rate_hz": 31.25,
  "window_samples": 64
}
```

Again, numeric values vary by window.

## Evidence checklist for a presentation

Capture or point to these lines in order:

1. `[edge]` or `[vibration-edge]`: inference occurred at the logical edge.
2. `[lorawan-tx]` and `[lorawan-payload]`: the edge formed a readable application result and encoded it into frames.
3. `[gateway]`: Webots radio frames were forwarded to the UDP backhaul.
4. `[lorawan-rx]`: the network server successfully verified and reconstructed the complete uplink.
5. `[network]`: the decoded event was published to its MQTT topic.
6. Raw MQTT subscriber output: the application event is visible after the network-server boundary.
7. `[cloud]` and dashboard row: the application server consumed, stored, and displayed it.

For a camera event, also show the Flask `POST /api/webots/capture` and `GET /uploads/...` lines to prove that the image used HTTP while the compact result used the LoRaWAN-style path.

## Logs that do not indicate inference

These repeated lines are dashboard/startup reads:

```text
GET /api/status
GET /api/events
GET /api/vibration-events
GET /api/health
```

They do not publish a sensor event and do not run YOLO or the vibration CNN.

## Gateway-log boundary

The edge prints selected application fields, and the network server prints the same decoded summary. The gateway itself sees and forwards only encrypted frames, so it prints transport metadata rather than decrypted content. No stage prints session keys. Use the raw MQTT subscriber after the network-server boundary when the complete decoded JSON is needed.
