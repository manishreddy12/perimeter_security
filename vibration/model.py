from __future__ import annotations

import torch
from torch import nn


WINDOW_SIZE = 64
SAMPLE_RATE_HZ = 31.25
CLASS_NAMES = ("normal", "vibration_anomaly")


class TinyVibrationCNN(nn.Module):
    """A compact two-layer 1D CNN for one-axis vibration windows."""

    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(1, 8, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(8, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.classifier = nn.Linear(16, len(CLASS_NAMES))

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(values).squeeze(-1))


def parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())
