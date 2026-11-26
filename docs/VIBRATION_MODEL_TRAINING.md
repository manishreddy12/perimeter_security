# Vibration model training and runtime values

## Purpose

This document explains how the 482-parameter vibration CNN is trained, what the Webots values mean, and which accuracy claims are valid.

Relevant files:

- `vibration/model.py`: architecture and constants
- `vibration/train_model.py`: synthetic generator and training loop
- `vibration/tiny_vibration_cnn.pt`: saved state dictionary
- `vibration/tiny_vibration_cnn.json`: checkpoint metadata
- `webots/controllers/vibration_edge/vibration_edge.py`: runtime signal generator and inference
- `vibration/payload.py`: compact result encoding

## Input representation

Each example is a one-axis vibration window:

| Property | Value |
| --- | --- |
| Samples per window | 64 |
| Sample rate | 31.25 Hz |
| Approximate duration | 2.048 seconds |
| Tensor shape per example | `1 x 64` |
| Classes | `normal`, `vibration_anomaly` |

The model receives a batch shaped `[batch, 1, 64]`.

## Reproducible training dataset

`synthetic_dataset()` uses NumPy random seed `20261122` and generates:

- 600 normal examples;
- 600 anomaly examples;
- 1,200 examples total.

The two classes are concatenated and shuffled with a reproducible permutation.

## Normal training signals

Normal examples start with Gaussian noise:

```text
mean = 0
standard deviation = 0.025
```

A weak low-frequency sinusoid is added independently to each example:

```text
frequency = uniform random value from 1 to 3 Hz
amplitude = uniform random value from 0 to 0.03
```

Conceptually:

```text
normal = small random noise + weak low-frequency movement
```

## Anomaly training signals

Anomaly examples use:

```text
frequency = uniform random value from 5 to 12 Hz
amplitude = uniform random value from 0.25 to 0.8
phase = uniform random value from 0 to 2*pi
noise standard deviation = 0.06
```

Conceptually:

```text
anomaly = strong 5-12 Hz sinusoid + random noise
```

The generated distributions are intentionally well separated, which makes this a pipeline demonstration rather than a difficult field-classification problem.

## CNN architecture

```text
Input: 1 x 64
  -> Conv1d(1, 8, kernel=5, padding=2)
  -> ReLU
  -> MaxPool1d(2)
  -> Conv1d(8, 16, kernel=3, padding=1)
  -> ReLU
  -> AdaptiveAvgPool1d(1)
  -> Linear(16, 2)
  -> normal or vibration_anomaly
```

The network has 482 trainable parameters.

## Training procedure

Training uses:

| Setting | Value |
| --- | --- |
| PyTorch random seed | `20261122` |
| Optimizer | Adam |
| Learning rate | `0.01` |
| Loss | Cross-entropy |
| Epochs | 80 |
| Batch strategy | All generated examples in one full batch |
| CPU threads | 1 |

After training, the script evaluates the model on the same generated examples used for training and saves:

- the state dictionary to `tiny_vibration_cnn.pt`;
- architecture/training metadata to `tiny_vibration_cnn.json`.

The currently recorded `training_accuracy` is `1.0`. This is training-set fit, not held-out test accuracy and not field accuracy.

## Retraining command

From the repository root:

```powershell
.\myenv\Scripts\python.exe -m vibration.train_model
```

This intentionally overwrites both the checkpoint and metadata. Run it only when model regeneration is intended, then rerun the automated tests.

## Webots runtime signal generation

The runtime controller uses a different reproducible seed, `2026`.

### Normal runtime window

Each sample begins as Gaussian noise:

```text
mean = 0
standard deviation = 0.01
```

### Demonstration anomaly

When an anomaly is active, the controller adds:

```text
frequency = 8 Hz
amplitude = 0.55
```

An anomaly is generated:

- automatically every fourth window;
- manually after `V` is pressed in the focused Edge-2 Webots view.

The controller subtracts the completed window's mean before creating the model tensor.

## Meaning of dashboard values

| Field | Calculation/meaning |
| --- | --- |
| `classification` | Class with maximum softmax probability |
| `confidence` | Softmax probability of the selected class |
| `rms_g` | Square root of the mean squared centered samples |
| `peak_g` | Maximum absolute centered sample |
| `latency_ms` | Measured CNN inference duration on the laptop CPU |
| `sample_rate_hz` | Configured 31.25 Hz |
| `window_samples` | Configured 64 samples |

The `g` suffix is an acceleration-like demonstration unit. These values are generated numbers, not calibrated measurements from a physical accelerometer.

Confidence can be close to 100% because runtime signals resemble the strongly separated synthetic training rules. It should not be interpreted as a calibrated real-world probability.

## Compact payload

`vibration/payload.py` packs a 29-byte little-endian application payload:

```text
16-byte event UUID
4-byte Unix timestamp
1-byte class index
2-byte confidence x 10,000
2-byte RMS x 10,000
2-byte peak x 10,000
2-byte latency milliseconds x 1,000
```

Model name, parameter count, rate, window size, resource profile and fixed `north-gate` zone are restored by the decoder after the network server receives the payload. The zone is device configuration, not an extra field in the 29 bytes.

Because the application payload is 29 bytes, it fits in one simulated LoRaWAN frame.

## What the current score proves

The current training result shows that:

- the CNN can learn the generated normal/anomaly rule;
- the checkpoint can be loaded at the logical edge;
- a 64-sample window can be classified;
- the result can be compactly encoded and transported;
- the application server can log and alert on the result.

It does not prove accuracy for a real fence, accelerometer, site or mounting arrangement.

## How to create a defensible physical evaluation

1. Mount a real accelerometer on the intended perimeter structure.
2. Record synchronized raw windows and independent video/manual labels.
3. Include wind, rain, animals, people, vehicles, impacts and maintenance activity.
4. Preserve device, location, date and session metadata.
5. Apply the same preprocessing during training and inference.
6. Split by session, day, site and device—not random neighbouring windows.
7. Report confusion matrix, precision, recall, macro F1 and false-alert rate.
8. Calibrate the alert threshold on validation data and report final results once on the held-out test set.

Until then, describe the model as a tiny CNN trained on reproducible synthetic vibration waveforms for demonstrating the edge-to-cloud pipeline.
