# Camera and vibration correlation ideas

## Current behavior

Camera and vibration are intentionally independent pipelines in the current implementation. They share the `north-gate` zone, matching Webots fence coordinates, application server, MQTT broker, simulated gateway infrastructure and dashboard, but they do not share an incident ID or fusion rule.

| Camera pipeline | Vibration pipeline |
| --- | --- |
| Event-driven image capture | Continuous 64-sample windows |
| YOLO11n | Tiny 1D CNN |
| JSON result, possibly fragmented | 29-byte binary result, one frame |
| Radio channel 40 | Radio channel 41 |
| Camera device address/session keys | Independent device address/session keys |
| `events` database table | `vibration_events` database table |

This separation is useful for modular testing and failure isolation. A vibration sensor can continue reporting when no camera event exists, and a camera event does not need to wait for a vibration window.

## Why events are not currently correlated

The implementation has no:

- common `incident_id` or `correlation_id`;
- zone bytes in the compact vibration payload (the fixed device-to-zone configuration restores `north-gate` after decoding);
- temporal join between the two database tables;
- combined severity rule;
- command path from a vibration result to camera capture;
- synchronized, independently labelled multimodal dataset.

The vibration payload contains a timestamp and its device identity determines the configured `north-gate` zone, so correlation can be added later without replacing either model.

## Recommended first improvement: cloud-side rule correlation

The simplest next step is a deterministic application-server rule. Associate `vibration-edge-01` with a configured zone such as `north-gate`, then search for camera and vibration events within a time window.

```text
vibration_anomaly at north-gate
  + camera person/vehicle within +/- 5 seconds
  -> high-priority correlated incident
```

This approach is easy to explain, test and audit. It does not require retraining either model.

## Example correlation matrix

| Camera result | Vibration result | Suggested interpretation | Severity |
| --- | --- | --- | --- |
| Normal | Normal | No incident | Low |
| Person/vehicle | Normal | Visual perimeter alert | Medium/high |
| Normal | Anomaly | Possible fence impact, tampering or maintenance event | Medium |
| Animal | Anomaly | Possible animal contact with the fence | Medium |
| Person/vehicle | Anomaly | Possible intrusion with physical perimeter contact | High |

These are project rules, not ground-truth conclusions. A person detector cannot determine authorization or intent.

## Suggested incident record

A future `incidents` table could contain:

```text
incident_id
zone_id
camera_event_id (nullable)
vibration_event_id (nullable)
first_event_at
last_event_at
severity
correlation_reason
acknowledged
```

Keep original camera and vibration rows unchanged and link them from the incident record. This preserves traceability.

## Implemented zone mapping without increasing the radio payload

The 29-byte vibration payload does not contain a zone string. Because the simulated sensor is fixed, the application uses this static mapping:

```text
vibration-edge-01 -> north-gate
simulated-edge-01 -> north-gate
```

This mapping is now represented by the shared `PERIMETER_ZONE` configuration. The network server restores `zone: north-gate` when it decodes the 29-byte vibration result, the application server stores it, and the dashboard displays it. This avoids sending repeated zone text in every low-bandwidth uplink. A physical deployment could provision the same mapping in device/application configuration.

## Vibration-triggered camera capture

A later version could capture an image when vibration is detected:

```text
vibration anomaly
  -> application/edge control decision
  -> request nearby camera capture
  -> camera inference
  -> link both events into one incident
```

The current LoRaWAN-style implementation is uplink-only. Two possible demonstration implementations are:

1. Add an MQTT command topic such as `perimeter/commands/camera/capture`. This is simpler but should be described as a simulated control path, not a LoRaWAN downlink.
2. Implement a simulated LoRaWAN downlink through the network server and Webots gateway. This matches the radio architecture more closely but adds frame direction, counters, receiver handling and tests.

No trigger path is implemented today.

## Possible combined risk score

A transparent rule can be used before considering multimodal ML:

```text
camera risk:
  normal=0, animal=1, person=2, vehicle=2

vibration risk:
  normal=0, anomaly=2

temporal bonus:
  +1 when both events occur in the same zone within 5 seconds
```

The application can convert the total into low, medium or high severity. Store the component scores and rule explanation so the result is auditable.

## Learned multimodal fusion

A learned fusion model should be attempted only after collecting synchronized camera and vibration data with independent incident labels. The dataset should include:

- people and vehicles with and without fence contact;
- animals contacting or passing near the perimeter;
- wind, rain and loose-fence vibration;
- maintenance work;
- sensor mounting differences;
- different times, sites and devices.

Split data by session, day, site and device rather than randomly mixing windows from the same recording. Until such data exists, rule-based temporal correlation is more defensible.

## Recommended staged plan

1. Leave the current independent pipelines unchanged for the present demo.
2. Use the implemented shared zone as the join key.
3. Add an `incidents` table and a +/-5-second rule.
4. Show correlated severity on the dashboard.
5. Optionally add vibration-triggered camera capture.
6. Consider learned fusion only after collecting real synchronized labels.
