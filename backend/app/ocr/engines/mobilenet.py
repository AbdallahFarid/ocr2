from __future__ import annotations

from typing import Tuple

import numpy as np

from app.ocr.labels import BankLabel


class MobileNetClassifier:
    """Scaffold for a MobileNetV3-based classifier.

    This is a placeholder engine; wiring for model loading and inference will be
    implemented when a trained model artifact is available.
    """

    def __init__(self, conf_threshold: float = 0.5, model_path: str | None = None) -> None:
        self.conf_threshold = conf_threshold
        self.model_path = model_path
        # TODO: load model when available

    def predict(self, image: np.ndarray) -> Tuple[str, float]:
        # TODO: perform real inference; for now return UNKNOWN with low confidence
        return BankLabel.UNKNOWN.value, 0.01
