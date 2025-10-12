from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional, Sequence, Dict, Any

import numpy as np
import os
import cv2

try:
    # PaddleOCR is an optional dependency; import lazily to avoid
    # import errors during testing when the library is not installed.
    from paddleocr import PaddleOCR  # type: ignore
except Exception:
    PaddleOCR = None  # type: ignore

# Import text normalization helpers. Prefer local utilities; fall back to
# legacy path; finally, use no-ops if neither is available.
try:  # prefer local utils in this repo
    from app.ocr.text_utils import fix_arabic_text, normalize_digits  # type: ignore
except Exception:
    try:
        from src.cheque_ocr.utils.text_utils import fix_arabic_text, normalize_digits  # type: ignore
    except Exception:
        # Fallback no‑op implementations if the helpers are unavailable.
        def fix_arabic_text(text: str) -> str:
            return text

        def normalize_digits(text: str) -> str:
            return text


@dataclass
class OCRLine:
    """Structured representation of a single OCR line.

    Attributes
    ----------
    text : str
        The normalized text of the line.
    raw_text : str
        The original text as returned by the OCR engine.
    confidence : float
        Confidence score reported by the OCR engine (0–1).
    bbox : List[Tuple[float, float]]
        Quadrilateral bounding box as returned by PaddleOCR in the form
        [(x1, y1), (x2, y2), (x3, y3), (x4, y4)].
    center : Tuple[float, float]
        Centroid (x, y) computed from the bounding box.  Useful for
        template‑based field location.
    lang : str
        Language code of the OCR engine used (e.g. ``"en"`` or ``"ar"``).
    engine : str
        Identifier of the OCR engine (e.g. ``"paddle"`` or ``"micr"``).
    """

    text: str
    raw_text: str
    confidence: float
    bbox: List[Tuple[float, float]]
    center: Tuple[float, float]
    lang: str
    engine: str


class PaddleOCREngine:
    """Wrapper around PaddleOCR for multi‑language cheque OCR.

    This engine supports both English (Latin) and Arabic models.  It
    caches the underlying PaddleOCR instances to avoid repeated
    initialisation overhead.  Use the ``ocr_image`` method to run
    recognition on a full cheque image and return a list of ``OCRLine``
    instances.  Use ``ocr_roi`` when you have a specific crop and
    wish to apply multi‑crop voting.
    """

    def __init__(self, use_angle_cls: bool = False) -> None:
        if PaddleOCR is None:
            raise ImportError(
                "PaddleOCR library is not installed. Please install paddleocr to use this engine."
            )
        self._ocr_en = None  # type: Optional[Any]
        self._ocr_ar = None  # type: Optional[Any]
        self.use_angle_cls = use_angle_cls

    def _get_engine(self, lang: str) -> Any:
        """Lazily instantiate and cache PaddleOCR engines.

        Parameters
        ----------
        lang : str
            Language code (``"en"`` or ``"ar"``).

        Returns
        -------
        PaddleOCR
            An instance of PaddleOCR configured for the requested language.
        """
        if lang == "en":
            if self._ocr_en is None:
                # Environment-driven fast defaults for CPU
                threads = int(os.getenv("OCR_THREADS", "8"))
                mkldnn = os.getenv("OCR_MKLDNN", "1") == "1"
                ocr_ver_en = os.getenv("OCR_VERSION_EN") or os.getenv("OCR_VERSION") or "PP-OCRv3"
                try:
                    rec_batch = int(os.getenv("OCR_REC_BATCH", "8"))
                except Exception:
                    rec_batch = 8
                try:
                    det_box_thresh = float(os.getenv("OCR_DET_BOX_THRESH", "-1"))
                except Exception:
                    det_box_thresh = -1.0
                try:
                    # Prefer explicit OCR version and disable angle/doc modules; avoid textline arg to prevent conflicts
                    self._ocr_en = PaddleOCR(
                        ocr_version=ocr_ver_en,
                        lang="en",
                        use_angle_cls=False,
                        enable_mkldnn=mkldnn,
                        cpu_threads=threads,
                        show_log=False,
                        # The following kwargs may not exist on some versions; handled by except
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        rec_batch_num=rec_batch,
                        **({"det_db_box_thresh": det_box_thresh} if det_box_thresh >= 0 else {}),
                    )
                except (TypeError, ValueError):
                    # Retry without optional doc/orientation kwargs (older PaddleOCR)
                    try:
                        self._ocr_en = PaddleOCR(
                            ocr_version=ocr_ver_en,
                            lang="en",
                            use_angle_cls=False,
                            enable_mkldnn=mkldnn,
                            cpu_threads=threads,
                            show_log=False,
                            rec_batch_num=rec_batch,
                        )
                    except Exception:
                        # Final fallback: language only, avoid enabling textline orientation
                        try:
                            self._ocr_en = PaddleOCR(lang="en", use_angle_cls=False, show_log=False, rec_batch_num=rec_batch)
                        except Exception:
                            self._ocr_en = PaddleOCR(lang="en")
            return self._ocr_en
        elif lang == "ar":
            if self._ocr_ar is None:
                # Environment-driven fast defaults for CPU
                threads = int(os.getenv("OCR_THREADS", "8"))
                mkldnn = os.getenv("OCR_MKLDNN", "1") == "1"
                ocr_ver_ar = os.getenv("OCR_VERSION_AR") or os.getenv("OCR_VERSION") or "PP-OCRv3"
                try:
                    rec_batch = int(os.getenv("OCR_REC_BATCH", "8"))
                except Exception:
                    rec_batch = 8
                try:
                    det_box_thresh = float(os.getenv("OCR_DET_BOX_THRESH", "-1"))
                except Exception:
                    det_box_thresh = -1.0
                try:
                    self._ocr_ar = PaddleOCR(
                        ocr_version=ocr_ver_ar,
                        lang="ar",
                        use_angle_cls=False,
                        enable_mkldnn=mkldnn,
                        cpu_threads=threads,
                        use_space_char=True,
                        show_log=False,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        rec_batch_num=rec_batch,
                        **({"det_db_box_thresh": det_box_thresh} if det_box_thresh >= 0 else {}),
                    )
                except (TypeError, ValueError):
                    try:
                        self._ocr_ar = PaddleOCR(
                            ocr_version=ocr_ver_ar,
                            lang="ar",
                            use_angle_cls=False,
                            enable_mkldnn=mkldnn,
                            cpu_threads=threads,
                            use_space_char=True,
                            show_log=False,
                            rec_batch_num=rec_batch,
                        )
                    except Exception:
                        try:
                            self._ocr_ar = PaddleOCR(lang="ar", use_angle_cls=False, use_space_char=True, show_log=False, rec_batch_num=rec_batch)
                        except Exception:
                            self._ocr_ar = PaddleOCR(lang="ar")
            return self._ocr_ar
        else:
            raise ValueError(f"Unsupported language: {lang}")

    @staticmethod
    def _compute_center(poly: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def _parse_results(
        self, results: Any, lang: str, min_confidence: float
    ) -> List[OCRLine]:
        """Convert raw PaddleOCR output to a list of ``OCRLine``.

        The PaddleOCR API may return results in different formats depending
        on the version.  This helper abstracts over those differences and
        filters out low‑confidence detections.  It also normalizes Arabic
        text and digits.
        """
        lines: List[OCRLine] = []
        if not results:
            return lines
        try:
            # Newer PaddleOCR returns [ { 'rec_texts': ..., 'rec_scores': ..., 'rec_polys': ... } ]
            res_obj = results[0]
            rec_texts = res_obj.get("rec_texts")
            rec_scores = res_obj.get("rec_scores")
            rec_polys = res_obj.get("rec_polys")
            if rec_texts and rec_scores and rec_polys:
                for text, score, poly in zip(rec_texts, rec_scores, rec_polys):
                    conf = float(score)
                    if conf < min_confidence:
                        continue
                    raw = str(text)
                    # Apply language‑specific normalization (logical form, no display shaping at OCR stage)
                    proc = fix_arabic_text(raw, for_display=False) if lang == "ar" else raw
                    proc = normalize_digits(proc)
                    poly_f = [(float(p[0]), float(p[1])) for p in poly]
                    center = self._compute_center(poly_f)
                    lines.append(
                        OCRLine(
                            text=proc,
                            raw_text=raw,
                            confidence=conf,
                            bbox=poly_f,
                            center=center,
                            lang=lang,
                            engine="paddle",
                        )
                    )
                return lines
        except Exception:
            pass
        # Older versions: results is [[ (bbox, (text, conf)) ]] structure
        if isinstance(results[0], list):
            for bbox, (text, conf) in results[0]:
                c = float(conf)
                if c < min_confidence:
                    continue
                raw = str(text)
                proc = fix_arabic_text(raw, for_display=False) if lang == "ar" else raw
                proc = normalize_digits(proc)
                poly_f = [(float(p[0]), float(p[1])) for p in bbox]
                center = self._compute_center(poly_f)
                lines.append(
                    OCRLine(
                        text=proc,
                        raw_text=raw,
                        confidence=c,
                        bbox=poly_f,
                        center=center,
                        lang=lang,
                        engine="paddle",
                    )
                )
        return lines

    def ocr_image(
        self,
        image: np.ndarray,
        languages: Optional[Sequence[str]] = None,
        min_confidence: float = 0.3,
    ) -> List[OCRLine]:
        """Run OCR on an entire cheque image with the specified languages.

        Parameters
        ----------
        image : np.ndarray
            RGB or BGR image array.  The engine will handle color
            ordering transparently.
        languages : sequence of str, optional
            Languages to use for recognition.  Defaults to ``["en", "ar"]``.
        min_confidence : float, optional
            Minimum confidence threshold for accepting a line.

        Returns
        -------
        List[OCRLine]
            A list of recognised text lines across all languages.  The
            list is not sorted; you may wish to sort by the `center` y
            coordinate in your caller.
        """
        if languages is None:
            languages = ("en", "ar")
        if image is None:
            return []
        # Convert PIL RGB to OpenCV BGR if needed.  PaddleOCR accepts
        # either ordering but BGR is conventional for OpenCV pipelines.
        if image.ndim == 3 and image.shape[2] == 3:
            # Heuristic: if the average of the first channel is much larger
            # than the third, assume RGB and convert to BGR.  Otherwise
            # assume it's already BGR.  This avoids unnecessary copies.
            if float(image[..., 0].mean()) > float(image[..., 2].mean()):
                img_cv = image[..., ::-1]
            else:
                img_cv = image
        else:
            img_cv = image
        all_lines: List[OCRLine] = []
        for lang in languages:
            engine = self._get_engine(lang)
            try:
                # Some PaddleOCR versions expose `ocr` attribute directly;
                # others use `predict`.  We try both for compatibility.
                try:
                    raw_results = engine.ocr(img_cv)
                except AttributeError:
                    raw_results = engine.predict(img_cv)
            except Exception as e:
                # Log and skip this language on failure.
                # Real implementation should use structured logging instead
                # of printing.
                print(f"PaddleOCR language {lang} failed: {e}")
                continue
            lines = self._parse_results(raw_results, lang=lang, min_confidence=min_confidence)
            all_lines.extend(lines)
        return all_lines

    def ocr_roi(
        self,
        image: np.ndarray,
        roi: Tuple[int, int, int, int],
        languages: Optional[Sequence[str]] = None,
        min_confidence: float = 0.3,
        padding: int = 5,
        n_votes: int = 3,
        max_width: Optional[int] = None,
    ) -> List[OCRLine]:
        """Run OCR on a region of interest using multi‑crop voting.

        The ROI is specified by pixel coordinates (x1, y1, x2, y2).  The
        engine crops the region, applies a few padded variants, runs
        OCR on each variant, and returns the highest scoring lines.

        Parameters
        ----------
        image : np.ndarray
            The full image.
        roi : tuple of int
            (x1, y1, x2, y2) coordinates defining the region of interest.
        languages : sequence of str, optional
            Languages to use.  Defaults to ``["en", "ar"]``.
        min_confidence : float, optional
            Minimum confidence threshold for accepting a line.
        padding : int, optional
            Number of pixels to pad around the ROI for each crop.
        n_votes : int, optional
            Number of padded crops to generate.  The padding increases
            linearly with each vote (e.g. p, 2p, 3p).

        Returns
        -------
        List[OCRLine]
            Lines from the best vote according to average confidence.  If
            no valid lines are found, returns an empty list.
        """
        if languages is None:
            languages = ("en", "ar")
        x1, y1, x2, y2 = roi
        h, w = image.shape[:2]
        candidates: List[Tuple[float, List[OCRLine]]] = []
        for i in range(n_votes):
            pad = (i + 1) * padding
            cx1 = max(0, x1 - pad)
            cy1 = max(0, y1 - pad)
            cx2 = min(w, x2 + pad)
            cy2 = min(h, y2 + pad)
            crop = image[cy1:cy2, cx1:cx2]
            # Optional downscale for ROI to speed up detection/recog
            try:
                if max_width is not None and crop.shape[1] > int(max_width):
                    scale = float(int(max_width)) / float(max(1, crop.shape[1]))
                    new_w = max(1, int(round(crop.shape[1] * scale)))
                    new_h = max(1, int(round(crop.shape[0] * scale)))
                    crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
            except Exception:
                pass
            lines = self.ocr_image(crop, languages=languages, min_confidence=min_confidence)
            if not lines:
                continue
            avg_conf = float(sum(l.confidence for l in lines)) / len(lines)
            candidates.append((avg_conf, lines))
        if not candidates:
            return []
        # Select the crop with the highest average confidence
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]


class MICREngine:
    """Placeholder for a specialized MICR OCR engine.

    The MICR line on a cheque uses special fonts (E‑13B or CMC7) that
    standard OCR engines struggle with.  A production implementation
    should load a model trained on MICR data and parse the magnetic
    character patterns into account numbers and cheque identifiers.
    Until such a model is available, this class provides a stub API
    compatible with ``PaddleOCREngine``.
    """

    def __init__(self) -> None:
        # In a real implementation you might load a custom Tesseract or
        # CNN model here.  Leave uninitialised for now.
        pass

    def ocr_image(self, image: np.ndarray, **_: Any) -> List[OCRLine]:
        # Stub: no MICR recognition implemented.
        # You can optionally raise a NotImplementedError here to make
        # missing MICR functionality explicit.
        return []

    def ocr_roi(self, image: np.ndarray, roi: Tuple[int, int, int, int], **_: Any) -> List[OCRLine]:
        return []