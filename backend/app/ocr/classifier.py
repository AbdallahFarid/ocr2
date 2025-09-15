from __future__ import annotations

from typing import Dict, Optional, Tuple
import os
from glob import glob

import numpy as np
import cv2

from app.config import DEFAULT_CLASSIFIER, ClassifierSettings
from app.ocr.labels import BankLabel
from app.ocr.engines.stub import StubClassifier
from app.ocr.engines.heuristic import HeuristicClassifier
from app.ocr.engines.mobilenet import MobileNetClassifier


class Classifier:
    """Classifier facade that selects an engine based on settings.

    Engines supported: stub | heuristic | mobilenet
    """

    def __init__(
        self,
        settings: Optional[ClassifierSettings] = None,
        heuristic_templates: Optional[Dict[str, np.ndarray]] = None,
    ) -> None:
        self.settings = settings or DEFAULT_CLASSIFIER
        engine_name = (self.settings.engine or "stub").lower()
        if engine_name == "stub":
            self._engine = StubClassifier(conf_threshold=self.settings.conf_threshold)
        elif engine_name == "heuristic":
            templates = dict(heuristic_templates or {})
            # Optionally load logo crops from directory
            if self.settings.heuristic_logo_dir and os.path.isdir(self.settings.heuristic_logo_dir):
                loaded = self._load_logo_templates(self.settings.heuristic_logo_dir)
                # Do not overwrite explicitly passed templates
                for k, v in loaded.items():
                    templates.setdefault(k, v)
            self._engine = HeuristicClassifier(
                templates=templates,
                conf_threshold=self.settings.conf_threshold,
            )
        elif engine_name == "mobilenet":
            self._engine = MobileNetClassifier(conf_threshold=self.settings.conf_threshold)
        else:
            # Fallback to stub for safety
            self._engine = StubClassifier(conf_threshold=self.settings.conf_threshold)

    def predict(self, image: np.ndarray) -> Tuple[str, float]:
        return self._engine.predict(image)

    @staticmethod
    def _load_logo_templates(directory: str) -> Dict[str, np.ndarray]:
        """Load logo crops from a directory.

        Mapping rule: filename (without extension) uppercased must match a BankLabel value
        e.g., 'FABMISR.png' -> 'FABMISR'. Non-matching files are ignored.
        """
        allowed = {lbl.value for lbl in BankLabel}
        templates: Dict[str, np.ndarray] = {}
        for path in glob(os.path.join(directory, "*")):
            if not os.path.isfile(path):
                continue
            name = os.path.splitext(os.path.basename(path))[0].upper()
            if name not in allowed:
                continue
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is None:
                continue
            templates[name] = img
        return templates


__all__ = ["Classifier", "BankLabel"]
