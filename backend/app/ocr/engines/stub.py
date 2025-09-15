from __future__ import annotations

from typing import Tuple
import numpy as np

from app.ocr.labels import BankLabel


class StubClassifier:
    """Deterministic stub classifier.

    Always returns QNB with a fixed confidence above default threshold so
    downstream pipeline can proceed in demo/test environments.
    """

    def __init__(self, conf_threshold: float = 0.5) -> None:
        self.conf_threshold = conf_threshold

    def predict(self, image: np.ndarray) -> Tuple[str, float]:
        label = BankLabel.QNB.value
        confidence = 0.60
        return label, confidence
