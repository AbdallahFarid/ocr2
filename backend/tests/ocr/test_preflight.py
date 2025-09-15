import numpy as np
import cv2
import pytest

from app.ocr.preflight import (
    PreflightConfig,
    PreflightError,
    preflight_process,
)


def _synthetic_text_image(width=600, height=300, angle_deg=8.0):
    img = np.full((height, width), 255, dtype=np.uint8)
    # Draw horizontal lines to simulate text
    for i in range(20, height, 20):
        cv2.putText(img, f"Line {i}", (20, i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
    # Rotate the image by angle_deg
    center = (width // 2, height // 2)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rot = cv2.warpAffine(img, M, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    # Convert to BGR for pipeline compatibility (it supports gray as well)
    return cv2.cvtColor(rot, cv2.COLOR_GRAY2BGR)


def _blur_image(img, ksize=9):
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


def test_preflight_success_and_metadata():
    img = _synthetic_text_image(angle_deg=7.0)
    cfg = PreflightConfig(
        blur_threshold=30.0,  # low to avoid rejection
        clahe_clip_limit=3.0,
        clahe_tile_grid=(8, 8),
        denoise_strength=7.0,
        max_deskew_angle_deg=15.0,
    )

    corr_id = "test-corr-123"
    corrected, meta = preflight_process(img, cfg=cfg, correlation_id=corr_id)

    assert corrected is not None and corrected.ndim == 2  # gray image
    assert isinstance(meta, dict)
    assert meta.get("correlation_id") == corr_id
    assert "blur_variance" in meta
    assert "deskew_angle_deg" in meta
    # Expect the deskew angle to be within allowed range
    assert abs(meta["deskew_angle_deg"]) <= cfg.max_deskew_angle_deg


def test_preflight_blur_rejection():
    img = _synthetic_text_image(angle_deg=0.0)
    img_blur = _blur_image(img, ksize=21)

    # Use high threshold to ensure rejection
    cfg = PreflightConfig(blur_threshold=2000.0)

    with pytest.raises(PreflightError) as excinfo:
        preflight_process(img_blur, cfg=cfg, correlation_id="corr-blur")

    err = excinfo.value
    assert err.code == "BLUR_TOO_LOW"
    assert "blur_variance" in err.meta
