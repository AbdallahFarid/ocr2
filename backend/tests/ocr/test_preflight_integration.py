import os
import glob
import cv2
import numpy as np
import pytest

from app.ocr.preflight import preflight_process, PreflightConfig


SAMPLES_DIR = os.path.join("data", "sample_images")


def _find_any_image() -> str | None:
    patterns = [
        os.path.join(SAMPLES_DIR, "FABMISR", "*.jpg"),
        os.path.join(SAMPLES_DIR, "FABMISR", "*.png"),
        os.path.join(SAMPLES_DIR, "QNB", "*.jpg"),
        os.path.join(SAMPLES_DIR, "QNB", "*.png"),
    ]
    for pat in patterns:
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


@pytest.mark.skipif(_find_any_image() is None, reason="No golden samples available under data/sample_images")
def test_preflight_on_golden_sample():
    path = _find_any_image()
    assert path is not None
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    assert img is not None

    # Use a forgiving threshold for integration
    cfg = PreflightConfig(blur_threshold=30.0)
    out, meta = preflight_process(img, cfg=cfg, correlation_id="itest-preflight-1")

    assert out is not None and out.ndim == 2
    assert isinstance(meta, dict)
    assert "blur_variance" in meta
    assert "deskew_angle_deg" in meta
