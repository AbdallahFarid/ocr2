from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.config import DEFAULT_CONFIDENCE  # type: ignore[attr-defined]


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def compute_field_confidence(
    ocr_conf: float,
    locator_conf: float,
    parse_ok: bool,
    *,
    parse_fail_factor: Optional[float] = None,
) -> float:
    """Compute field confidence = ocr_conf × locator_conf × parse_factor.

    parse_factor = 1.0 if parse_ok else parse_fail_factor (default from config).
    Values are clamped to [0, 1].
    """
    pff = parse_fail_factor if parse_fail_factor is not None else getattr(DEFAULT_CONFIDENCE, "parse_fail_factor", 0.97)
    o = _clamp01(ocr_conf)
    l = _clamp01(locator_conf)
    pf = 1.0 if parse_ok else _clamp01(pff)
    return _clamp01(o * l * pf)


def passes_global_threshold(field_conf: float, *, threshold: Optional[float] = None) -> bool:
    thr = threshold if threshold is not None else getattr(DEFAULT_CONFIDENCE, "global_threshold", 0.995)
    return _clamp01(field_conf) >= float(thr)
