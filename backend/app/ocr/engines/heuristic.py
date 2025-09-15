from __future__ import annotations

from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from app.ocr.labels import BankLabel


class HeuristicClassifier:
    """Lightweight heuristic classifier.

    Two modes:
    1) Template matching if templates are provided per label.
    2) Fallback layout heuristic: compare brightness in top-left vs top-right bands.
       - Darker left region => QNB
       - Darker right region => FABMISR
       - Otherwise => UNKNOWN
    """

    def __init__(
        self,
        templates: Optional[Dict[str, np.ndarray]] = None,
        conf_threshold: float = 0.5,
    ) -> None:
        self.templates = templates or {}
        self.conf_threshold = conf_threshold

    def _predict_with_templates(self, image: np.ndarray) -> Tuple[str, float]:
        gray = self._to_gray(image)
        best_label = BankLabel.UNKNOWN.value
        best_score = -1.0

        for label, templ in self.templates.items():
            templ_gray = self._to_gray(templ)
            if gray.shape[0] < templ_gray.shape[0] or gray.shape[1] < templ_gray.shape[1]:
                # Template larger than image; skip
                continue
            res = cv2.matchTemplate(gray, templ_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_label = label
        if best_score >= self.conf_threshold:
            return best_label, float(best_score)
        return BankLabel.UNKNOWN.value, float(max(0.0, best_score))

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    def _predict_with_layout(self, image: np.ndarray) -> Tuple[str, float]:
        gray = self._to_gray(image)
        h, w = gray.shape[:2]
        if h == 0 or w == 0:
            return BankLabel.UNKNOWN.value, 0.0
        band_h = max(1, int(0.25 * h))
        band_w = max(1, int(0.25 * w))
        left = gray[0:band_h, 0:band_w]
        right = gray[0:band_h, w - band_w : w]
        left_mean = float(np.mean(left))
        right_mean = float(np.mean(right))
        diff = right_mean - left_mean  # positive => left darker
        # Map difference to [0, 1]
        conf = min(0.99, max(0.0, abs(diff) / 32.0))
        if diff > 5.0 and conf >= self.conf_threshold:
            return BankLabel.QNB.value, conf
        if diff < -5.0 and conf >= self.conf_threshold:
            return BankLabel.FABMISR.value, conf
        return BankLabel.UNKNOWN.value, conf

    def predict(self, image: np.ndarray) -> Tuple[str, float]:
        if self.templates:
            label, conf = self._predict_with_templates(image)
            if conf >= self.conf_threshold and label != BankLabel.UNKNOWN.value:
                return label, conf
        return self._predict_with_layout(image)
