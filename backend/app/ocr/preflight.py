from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import logging
from app.config import DEFAULT_PREFLIGHT


@dataclass
class PreflightConfig:
    """Configuration for preflight processing.

    - blur_threshold: Laplacian variance threshold below which an image is considered blurry
    - clahe_clip_limit: Contrast Limited AHE clip limit
    - clahe_tile_grid: tile grid size used for CLAHE
    - denoise_strength: strength for denoising (higher removes more noise)
    - max_deskew_angle_deg: maximum absolute angle to deskew (safety)
    """

    blur_threshold: float = 120.0
    clahe_clip_limit: float = 3.0
    clahe_tile_grid: Tuple[int, int] = (8, 8)
    denoise_strength: float = 7.0
    max_deskew_angle_deg: float = 15.0


class PreflightError(Exception):
    def __init__(self, code: str, message: str, meta: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.meta = meta or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "meta": self.meta}


def _to_gray(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def _enhance_contrast(gray: np.ndarray, cfg: PreflightConfig) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=cfg.clahe_clip_limit, tileGridSize=cfg.clahe_tile_grid)
    return clahe.apply(gray)


def _denoise(gray: np.ndarray, cfg: PreflightConfig) -> np.ndarray:
    # Bilateral filter preserves edges better than Gaussian for text
    return cv2.bilateralFilter(gray, d=5, sigmaColor=cfg.denoise_strength * 12, sigmaSpace=cfg.denoise_strength)


def _laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _estimate_skew_angle(gray: np.ndarray, max_abs_angle: float = 15.0) -> float:
    # Use Canny + Hough to estimate dominant text line angle
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180.0, threshold=150)
    if lines is None:
        return 0.0
    angles = []
    for rho_theta in lines[:100]:
        rho, theta = rho_theta[0]
        angle = (theta * 180.0 / np.pi) - 90.0  # convert to degrees, 0 is horizontal text line
        # Normalize to [-90, 90]
        if angle > 90:
            angle -= 180
        if angle < -90:
            angle += 180
        # Keep modest angles only
        if abs(angle) <= max_abs_angle:
            angles.append(angle)
    if not angles:
        return 0.0
    # Use median for robustness
    return float(np.median(angles))


def _deskew(gray: np.ndarray, angle_deg: float) -> np.ndarray:
    if abs(angle_deg) < 0.1:
        return gray
    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return rotated


def preflight_process(
    image: np.ndarray,
    cfg: Optional[PreflightConfig] = None,
    correlation_id: Optional[str] = None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Run preflight pipeline on a single image.

    Returns a tuple of (processed_image, meta) where meta contains metrics such as
    blur_variance, deskew_angle_deg and correlation_id.

    Raises PreflightError with code 'BLUR_TOO_LOW' when blur is below threshold.
    """
    if cfg is None:
        # Use central settings by default
        cfg = PreflightConfig(
            blur_threshold=DEFAULT_PREFLIGHT.blur_threshold,
            clahe_clip_limit=DEFAULT_PREFLIGHT.clahe_clip_limit,
            clahe_tile_grid=DEFAULT_PREFLIGHT.clahe_tile_grid,
            denoise_strength=DEFAULT_PREFLIGHT.denoise_strength,
            max_deskew_angle_deg=DEFAULT_PREFLIGHT.max_deskew_angle_deg,
        )
    logger = logging.getLogger("backend.app.ocr.preflight")
    logger.info("preflight_start", extra={"correlation_id": correlation_id})

    # Convert to gray first
    gray = _to_gray(image)

    # Blur detection on original gray
    blur_var = _laplacian_variance(gray)
    logger.debug("blur_variance_computed", extra={"correlation_id": correlation_id, "blur_variance": blur_var})
    if blur_var < cfg.blur_threshold:
        raise PreflightError(
            code="BLUR_TOO_LOW",
            message="Image rejected due to low sharpness",
            meta={"blur_variance": blur_var, "threshold": cfg.blur_threshold, "correlation_id": correlation_id},
        )

    # Denoise
    gray_dn = _denoise(gray, cfg)

    # Contrast enhancement
    gray_ce = _enhance_contrast(gray_dn, cfg)

    # Estimate skew and deskew within allowed range
    est_angle = _estimate_skew_angle(gray_ce, max_abs_angle=cfg.max_deskew_angle_deg)
    corrected = _deskew(gray_ce, est_angle)
    logger.debug(
        "deskew_complete",
        extra={"correlation_id": correlation_id, "deskew_angle_deg": est_angle},
    )

    meta: Dict[str, Any] = {
        "correlation_id": correlation_id,
        "blur_variance": blur_var,
        "deskew_angle_deg": est_angle,
    }

    logger.info("preflight_complete", extra={"correlation_id": correlation_id, **meta})
    return corrected, meta


__all__ = [
    "PreflightConfig",
    "PreflightError",
    "preflight_process",
]
