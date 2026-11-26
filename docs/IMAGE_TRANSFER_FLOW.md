# RGB image transfer flow

## Key design rule

RGB image bytes do not travel through MQTT or the simulated LoRaWAN frames. Images use local HTTP. MQTT and the radio path carry metadata, detections, confidence, bounding boxes and decisions.

This split reflects the intended physical design: LoRaWAN is suitable for compact alerts and sensor results, while selected images require Wi-Fi, Ethernet, cellular or another IP-capable link.

## Webots camera capture

```text
Webots Camera device
  -> BGRA frame in controller memory
  -> OpenCV converts BGRA to BGR
  -> JPEG encoding
  -> HTTP multipart POST /api/webots/capture
  -> Flask validates and stores temporary JPEG in memory
  -> HTTP 201 returns event_id and image_url
  -> YOLO11n runs on the original controller frame
  -> compact detection result carries image_url over simulated LoRaWAN
  -> network server publishes result through MQTT
  -> application server GETs image_url for annotation or YOLO11m
```

The Webots edge does not download its own image before YOLO11n. It already has the captured frame and calls `predict_frame(image)`.

## Webots capture sequence

1. The camera controller captures a Webots image automatically at startup or after `C`.
2. OpenCV converts and JPEG-encodes it.
3. The controller calls `POST /api/webots/capture` with multipart field `image`.
4. Flask reads no more than 8 MB, verifies that OpenCV can decode the data, limits the longest side to 1600 pixels and encodes a JPEG at quality 90.
5. Flask stores the JPEG in the in-memory upload store and returns metadata such as:

   ```json
   {
     "event_id": "uuid",
     "camera_id": "webots-camera",
     "image_name": "webots-camera.jpg",
     "image_url": "http://127.0.0.1:8000/uploads/<upload-id>",
     "source": "upload"
   }
   ```

6. The controller adds Webots position and device-profile metadata.
7. YOLO11n runs on the controller's frame.
8. The edge result, including the temporary URL, travels through the radio/gateway/network-server path.
9. The application server uses `GET /uploads/<upload-id>` to retrieve the JPEG.

## What the application server does with the image

### Edge result accepted

```text
selected_location=edge
  -> application server GETs image_url
  -> does not run YOLO11m
  -> OpenCV draws YOLO11n boxes
  -> annotated JPEG stored as Base64 in SQLite
```

### Cloud verification selected

```text
selected_location=cloud
  -> application server GETs image_url
  -> runs YOLO11m at 640 px
  -> OpenCV draws YOLO11m boxes
  -> annotated JPEG stored as Base64 in SQLite
```

The browser displays the server-generated Base64 annotated JPEG. Browser JavaScript does not calculate detections or draw boxes.

## Built-in dashboard sample

```text
Browser POST /api/run with sample key
  -> Flask builds static image_url
  -> metadata and URL published through MQTT
  -> edge GETs /static/<sample>.jpg
  -> YOLO11n
  -> in Webots mode, compact result uses radio/gateway/network server
  -> application server accepts edge result or runs YOLO11m
```

The sample key and neutral sample name contain no answer label.

## Browser upload

```text
Browser image bytes
  -> HTTP POST /api/upload
  -> Flask validates/resizes/JPEG-encodes
  -> temporary GET /uploads/<id> URL
  -> URL plus metadata published through MQTT
  -> edge downloads URL and runs YOLO11n
  -> compact result returns through selected result path
  -> application server downloads URL for final processing
```

The server holds at most 20 temporary images in memory. Upload bytes are not durable, and upload-sourced database records are removed during the next application initialization because their URLs are no longer valid.

## Terminal evidence

A Webots capture typically shows:

```text
127.0.0.1 - - [...] "POST /api/webots/capture HTTP/1.1" 201 -
[edge] webots-camera.jpg -> normal -> edge (<latency> ms)
[lorawan-payload][edge-1] object=normal confidence=0.0% boxes=0 decision=edge image_ref=HTTP_URL
[lorawan-rx][edge-1] zone=north-gate event=<event> fragments=<count> object=normal boxes=0 decision=edge
[network] event=<event> -> MQTT perimeter/edge/simulated-edge-01/result
127.0.0.1 - - [...] "GET /uploads/<upload-id> HTTP/1.1" 200 -
[cloud] <event-prefix> zone=north-gate -> edge -> normal
```

How to read it:

- `POST /api/webots/capture`: JPEG moved from Webots to the temporary HTTP store.
- `[edge]`: YOLO11n processed the frame.
- `[lorawan-payload][edge-1]`: readable compact-result summary; `image_ref=HTTP_URL` confirms that pixels are not in the radio payload.
- `[lorawan-rx][edge-1]`: compact result completed decoding and reassembly.
- `[network]`: decoded result entered MQTT.
- `GET /uploads/...`: application server retrieved the JPEG using the URL carried in the result.
- `[cloud]`: event was annotated and stored, with YOLO11m only if selected.

## What travels over each link

| Link | Data |
| --- | --- |
| Webots camera -> Flask HTTP | JPEG bytes |
| Browser -> Flask HTTP | Sample key or uploaded image bytes |
| Camera-input MQTT | Event ID, name, zone, source and image URL |
| Simulated LoRaWAN result | Summary, detections, bounding boxes, confidence, latency, decision and image URL |
| Network server -> MQTT | Reconstructed application result JSON |
| Flask image GET | JPEG bytes |
| SQLite camera record | Metadata, detections and Base64 annotated JPEG |

## Presentation wording

> The image is too large for LoRaWAN, so it is transferred through a local HTTP image path. The edge performs YOLO11n on the frame and sends only the compact result through the simulated LoRaWAN gateway. If cloud verification is selected, the application server retrieves the image through its URL and runs YOLO11m.

Do not say that the JPEG is transmitted through MQTT or LoRaWAN.
