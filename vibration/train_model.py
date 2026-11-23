from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

from vibration.model import CLASS_NAMES, SAMPLE_RATE_HZ, WINDOW_SIZE, TinyVibrationCNN, parameter_count


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "tiny_vibration_cnn.pt"
METADATA_PATH = ROOT / "tiny_vibration_cnn.json"


def synthetic_dataset(samples_per_class: int = 600) -> tuple[torch.Tensor, torch.Tensor]:
    """Create reproducible demonstration signals with no field-accuracy claim."""
    generator = np.random.default_rng(20261122)
    time_axis = np.arange(WINDOW_SIZE, dtype=np.float32) / SAMPLE_RATE_HZ
    normal = generator.normal(0.0, 0.025, (samples_per_class, WINDOW_SIZE)).astype(np.float32)
    normal += generator.uniform(0.0, 0.03, (samples_per_class, 1)).astype(np.float32) * np.sin(
        2 * np.pi * generator.uniform(1.0, 3.0, (samples_per_class, 1)) * time_axis
    )

    amplitude = generator.uniform(0.25, 0.8, (samples_per_class, 1)).astype(np.float32)
    frequency = generator.uniform(5.0, 12.0, (samples_per_class, 1)).astype(np.float32)
    phase = generator.uniform(0.0, 2 * np.pi, (samples_per_class, 1)).astype(np.float32)
    anomaly = amplitude * np.sin(2 * np.pi * frequency * time_axis + phase)
    anomaly += generator.normal(0.0, 0.06, anomaly.shape).astype(np.float32)

    features = np.concatenate((normal, anomaly))[:, None, :]
    labels = np.concatenate(
        (np.zeros(samples_per_class, dtype=np.int64), np.ones(samples_per_class, dtype=np.int64))
    )
    order = generator.permutation(len(labels))
    return torch.from_numpy(features[order]), torch.from_numpy(labels[order])


def main() -> None:
    torch.manual_seed(20261122)
    torch.set_num_threads(1)
    features, labels = synthetic_dataset()
    model = TinyVibrationCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    loss_function = nn.CrossEntropyLoss()
    model.train()
    for _ in range(80):
        optimizer.zero_grad()
        loss = loss_function(model(features), labels)
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        accuracy = float((model(features).argmax(dim=1) == labels).float().mean())
    torch.save(model.state_dict(), MODEL_PATH)
    metadata = {
        "model": "TinyVibrationCNN",
        "classes": list(CLASS_NAMES),
        "window_size": WINDOW_SIZE,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "parameters": parameter_count(model),
        "training_source": "synthetic demonstration signals",
        "training_accuracy": round(accuracy, 4),
        "limitation": "Training accuracy measures synthetic-rule fit, not field accuracy.",
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
