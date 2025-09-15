from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Tuple, Optional


@dataclass
class PreflightSettings:
    blur_threshold: float = float(os.getenv("PREFLIGHT_BLUR_THRESHOLD", 120.0))
    clahe_clip_limit: float = float(os.getenv("PREFLIGHT_CLAHE_CLIP", 3.0))
    clahe_tile_grid: Tuple[int, int] = (
        int(os.getenv("PREFLIGHT_CLAHE_TILE_X", 8)),
        int(os.getenv("PREFLIGHT_CLAHE_TILE_Y", 8)),
    )
    denoise_strength: float = float(os.getenv("PREFLIGHT_DENOISE_STRENGTH", 7.0))
    max_deskew_angle_deg: float = float(os.getenv("PREFLIGHT_MAX_DESKEW_DEG", 15.0))


DEFAULT_PREFLIGHT = PreflightSettings()


@dataclass
class ClassifierSettings:
    engine: str = os.getenv("CLASSIFIER_ENGINE", "stub")  # stub | heuristic | mobilenet
    conf_threshold: float = float(os.getenv("CLASSIFIER_CONF_THRESHOLD", 0.5))
    heuristic_logo_dir: Optional[str] = os.getenv("CLASSIFIER_HEURISTIC_LOGO_DIR") or None


DEFAULT_CLASSIFIER = ClassifierSettings()
