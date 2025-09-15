from __future__ import annotations

from typing import Dict, Tuple


def clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def norm_rect_to_pixels(image_shape: Tuple[int, int], roi_norm: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    """Convert normalized [x,y,w,h] (0..1) to integer pixel bbox [x1,y1,x2,y2].

    image_shape: (height, width)
    """
    h, w = image_shape
    x, y, rw, rh = roi_norm
    x = clip01(x)
    y = clip01(y)
    rw = clip01(rw)
    rh = clip01(rh)
    x1 = int(round(x * w))
    y1 = int(round(y * h))
    x2 = int(round((x + rw) * w))
    y2 = int(round((y + rh) * h))
    x1 = max(0, min(x1, w - 1))
    y1 = max(0, min(y1, h - 1))
    x2 = max(0, min(max(x2, x1 + 1), w))
    y2 = max(0, min(max(y2, y1 + 1), h))
    return x1, y1, x2, y2


def pixel_center(bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return cx, cy


__all__ = ["norm_rect_to_pixels", "pixel_center", "clip01"]
