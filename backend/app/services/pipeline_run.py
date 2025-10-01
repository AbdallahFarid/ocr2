from __future__ import annotations
import re
import os
import numpy as np
from typing import Optional, List, Dict, Any, Tuple, Union

def correct_aaib_date_text(text: str) -> str:
    """Apply AAIB-specific date corrections to fix common OCR errors.
    
    Common patterns: OcU->Oct, JuV->Jul, Datc->Date, Dale->Date, 0ct->Oct
    """
    if not text:
        return text
    # Fix malformed date prefixes like "Datc", "Dale", or "Date" at beginning
    text = re.sub(r'^(?:Datc|Date|Dale)\s*', '', text, flags=re.IGNORECASE)
    # Also strip "Date" or "Dale" prefixes without anchor (mid-string)
    text = re.sub(r'\b(?:Date|Dale)[-\s]*', '', text, flags=re.IGNORECASE)
    # Fix malformed months
    text = re.sub(r'\bJuV\b', 'Jul', text, flags=re.IGNORECASE)
    text = re.sub(r'\bOcU\b', 'Oct', text, flags=re.IGNORECASE)
    text = re.sub(r'\b0ct\b', 'Oct', text, flags=re.IGNORECASE)
    text = re.sub(r'\b0ec\b', 'Dec', text, flags=re.IGNORECASE)
    text = re.sub(r'\bocv\b', 'Oct', text, flags=re.IGNORECASE)
    text = re.sub(r'\bju1\b', 'Jul', text, flags=re.IGNORECASE)
    return text

def correct_nbe_date_text(text: str) -> str:
    """Apply NBE-specific date corrections to fix common OCR month errors.

    Examples seen: 'lan'->'Jan', 'lul'->'Jul', tolerate '0ct'/'0ec', 'lct'->'Oct'.
    Also strip leading 'Date'/'Datc'.
    """
    if not text:
        return text
    # Strip leading label
    text = re.sub(r'^(?:Datc|Date)\s*', '', text)
    # Month corrections
    text = re.sub(r"\blan\b", "Jan", text, flags=re.IGNORECASE)
    text = re.sub(r"\blul\b", "Jul", text, flags=re.IGNORECASE)
    text = re.sub(r"\blct\b", "Oct", text, flags=re.IGNORECASE)
    text = re.sub(r"\b0ct\b", "Oct", text, flags=re.IGNORECASE)
    text = re.sub(r"\b0ec\b", "Dec", text, flags=re.IGNORECASE)
    return text

import cv2
import numpy as np
import json
from datetime import datetime, timezone
import os

from app.ocr import PaddleOCREngine
from app.pipeline.postprocess import parse_and_normalize
from app.validations.confidence import compute_field_confidence, passes_global_threshold
from app.ocr.locator import locate_fields
from app.ocr.text_utils import fix_arabic_text
from app.utils.profiling import get_current_profiler

AMOUNT_RX = re.compile(r"\b\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})?\b")
AMOUNT_DEC_RX = re.compile(r"\b\d{1,3}(?:[\.,]\d{3})*[\.,]\d{2}\b")
# Accept dates like 30/Apr/2030, 30-Apr-2030, allow missing separators and extra punctuation,
# tolerate '0ct'/'0ec' OCR variants for Oct/Dec, and tolerate trailing -1 or .1 from OCR noise.
# No leading word boundary required.
DATE_RX = re.compile(r"(?i)(?<!\d)\d{1,2}\s*[\/\-\.]?\s*(?:0ct|0ec|[A-Za-z]{3})\s*[\/\-\.]?\s*\d{2,4}(?:[-\.]\d{1,2})?(?!\d)")
NUM_RX = re.compile(r"\b\d{6,}\b")
LABEL_NO_RX = re.compile(r"\b[nN][oO0]\b")
# Global toggle: mute 'name' field and skip Arabic OCR for performance
MUTE_NAME = os.getenv("MUTE_NAME", "1") == "1"


def _load_image(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Failed to read image: {path}")
    return img


def _maybe_downscale(img: np.ndarray, *, max_width: Optional[int] = None) -> np.ndarray:
    """Downscale very large cheques to speed up OCR and avoid engine stalls.

    Preserves aspect ratio. Uses INTER_AREA for quality downscaling.
    """
    try:
        h, w = img.shape[:2]
    except Exception:
        return img
    if max_width is None:
        try:
            max_width = int(os.getenv("OCR_MAX_WIDTH", "1400"))
        except Exception:
            max_width = 1400
    if w <= max_width:
        return img
    scale = float(max_width) / float(max(1, w))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    try:
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except Exception:
        return img


_ENGINE_SINGLETON: Optional[PaddleOCREngine] = None
_ENGINE_WARMED: bool = False


def _get_engine() -> PaddleOCREngine:
    global _ENGINE_SINGLETON
    global _ENGINE_WARMED
    if _ENGINE_SINGLETON is None:
        _ENGINE_SINGLETON = PaddleOCREngine()
    # Warm up once to trigger model downloads/initialization, avoiding first-call stalls
    if not _ENGINE_WARMED:
        try:
            dummy = np.full((32, 32, 3), 255, dtype=np.uint8)
            _ENGINE_SINGLETON.ocr_image(dummy, languages=["en"], min_confidence=0.9)
            if not MUTE_NAME:
                _ENGINE_SINGLETON.ocr_image(dummy, languages=["ar"], min_confidence=0.9)
            _ENGINE_WARMED = True
        except Exception:
            # Ignore warmup failures; real call will try again
            _ENGINE_WARMED = True
    return _ENGINE_SINGLETON


def _ocr_lines_for_locator(lines: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for l in lines:
        out.append({
            "text": l.text,
            "confidence": float(l.confidence),
            "pos": [int(round(l.center[0])), int(round(l.center[1]))],
        })
    return out


def _serialize_ocr_lines(lines: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for l in lines:
        try:
            out.append({
                "text": l.text,
                "raw_text": l.raw_text,
                "confidence": float(l.confidence),
                "lang": getattr(l, "lang", None),
                "engine": getattr(l, "engine", None),
                "bbox": [[float(p[0]), float(p[1])] for p in l.bbox],
                "center": [float(l.center[0]), float(l.center[1])],
            })
        except Exception:
            # Best-effort; skip malformed entries
            continue
    return out


def _write_raw_ocr_lines(bank: str, image_path: str, lines: List[Any]) -> None:
    try:
        file_id = os.path.basename(image_path)
        root = os.getenv("OCR_LINES_ROOT", os.path.join("backend", "reports", "ocr_lines"))
        out_dir = os.path.join(root, bank)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{file_id}.json")
        payload = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bank": bank,
            "file": file_id,
            "count": len(lines),
            "lines": _serialize_ocr_lines(lines),
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        # Do not break the pipeline if writing fails
        pass


def _select_best_text(field: str, lines: List[Any]) -> Tuple[str, float, str]:
    if not lines:
        return "", 0.0, ""
    items = [
        {"text": str(l.text), "confidence": float(l.confidence), "lang": str(l.lang)} for l in lines
    ]
    candidates = items
    if field == "amount_numeric":
        cand_dec = [l for l in items if AMOUNT_DEC_RX.search(l["text"])]
        if cand_dec:
            candidates = cand_dec
        else:
            cand = [l for l in items if AMOUNT_RX.search(l["text"])]
            if cand:
                candidates = cand
    elif field == "date":
        cand = [l for l in items if DATE_RX.search(l["text"])]
        if cand:
            candidates = cand
    elif field == "cheque_number":
        cand = [l for l in items if NUM_RX.search(l["text"])]
        if cand:
            candidates = cand
    best = max(candidates, key=lambda l: l["confidence"])
    return best["text"], best["confidence"], best["lang"]


def _best_text_from_roi(
    engine: PaddleOCREngine,
    img: np.ndarray,
    bbox: Tuple[int, int, int, int],
    field: str,
    min_conf: float,
    full_lines: Optional[List[Any]] = None,
) -> Tuple[str, float, str]:
    if field == "name" and MUTE_NAME:
        # Skip OCR entirely for name to speed up processing
        return "", 0.0, ""
    langs = ["ar"] if (field == "name" and not MUTE_NAME) else ["en"]
    h, w = img.shape[:2]
    # Fast path: try selecting from full-image OCR lines inside the ROI first (avoid re-OCR)
    bx1, by1, bx2, by2 = bbox
    prof = get_current_profiler()
    if full_lines:
        if prof is not None:
            with prof.span("roi_from_full", field=field):
                try:
                    cand = [
                        l for l in full_lines
                        if (bx1 <= float(getattr(l, "center", (0.0, 0.0))[0]) <= bx2)
                        and (by1 <= float(getattr(l, "center", (0.0, 0.0))[1]) <= by2)
                    ]
                except Exception:
                    cand = []
                if cand:
                    t0, c0, lang0 = _select_best_text(field, cand)
                    ok = True
                    if field == "date" and not DATE_RX.search(t0 or ""):
                        ok = False
                    if field == "amount_numeric" and not (AMOUNT_DEC_RX.search(t0 or "") or AMOUNT_RX.search(t0 or "")):
                        ok = False
                    if field == "cheque_number" and not re.search(r"\b\d{6,}\b", t0 or ""):
                        ok = False
                    if ok:
                        return t0, c0, lang0
        else:
            try:
                cand = [
                    l for l in full_lines
                    if (bx1 <= float(getattr(l, "center", (0.0, 0.0))[0]) <= bx2)
                    and (by1 <= float(getattr(l, "center", (0.0, 0.0))[1]) <= by2)
                ]
            except Exception:
                cand = []
            if cand:
                t0, c0, lang0 = _select_best_text(field, cand)
                ok = True
                if field == "date" and not DATE_RX.search(t0 or ""):
                    ok = False
                if field == "amount_numeric" and not (AMOUNT_DEC_RX.search(t0 or "") or AMOUNT_RX.search(t0 or "")):
                    ok = False
                if field == "cheque_number" and not re.search(r"\b\d{6,}\b", t0 or ""):
                    ok = False
                if ok:
                    return t0, c0, lang0

    # Env-tunable ROI parameters
    try:
        base_votes = max(1, int(os.getenv("ROI_VOTES", "1")))
    except Exception:
        base_votes = 1
    try:
        pad_px = int(os.getenv("ROI_PADDING", "6"))
    except Exception:
        pad_px = 6
    # Optional ROI downscale width
    try:
        _roi_mw = int(os.getenv("ROI_MAX_WIDTH", "0"))
        roi_max_w: Optional[int] = _roi_mw if _roi_mw > 0 else None
    except Exception:
        roi_max_w = None
    if prof is not None:
        with prof.span("roi_ocr", field=field, votes=base_votes, padding=pad_px, w=w, h=h):
            lines = engine.ocr_roi(
                img,
                roi=bbox,
                languages=langs,
                min_confidence=min_conf,
                padding=pad_px,
                n_votes=base_votes,
                max_width=roi_max_w,
            )
    else:
        lines = engine.ocr_roi(
            img,
            roi=bbox,
            languages=langs,
            min_confidence=min_conf,
            padding=pad_px,
            n_votes=base_votes,
            max_width=roi_max_w,
        )
    if not lines:
        return "", 0.0, ""
    # Special handling for Arabic names: merge multiple fragments with stable RTL ordering
    if field == "name":
        # Group by y-band (same visual line), then within each group sort by x desc (RTL)
        try:
            centers = [
                (
                    float(getattr(l, "center", (0.0, 0.0))[0]) if hasattr(l, "center") else 0.0,
                    float(getattr(l, "center", (0.0, 0.0))[1]) if hasattr(l, "center") else 0.0,
                    idx,
                    l,
                )
                for idx, l in enumerate(lines)
            ]
        except Exception:
            centers = [(0.0, 0.0, idx, l) for idx, l in enumerate(lines)]

        # Cluster by y using a tolerance (5% of image height)
        y_tol = 0.05 * h
        groups: list[list[tuple[float, float, int, Any]]] = []
        for cx, cy, i_ord, l in sorted(centers, key=lambda t: t[1]):  # sort by y asc
            placed = False
            for g in groups:
                # Compare to group's median y
                gy_vals = [yy for _, yy, _, _ in g]
                gy = sum(gy_vals) / max(1, len(gy_vals))
                if abs(cy - gy) <= y_tol:
                    g.append((cx, cy, i_ord, l))
                    placed = True
                    break
            if not placed:
                groups.append([(cx, cy, i_ord, l)])

        # Sort groups by y asc, each group by x desc (RTL)
        groups.sort(key=lambda g: sum(yy for _, yy, _, _ in g) / max(1, len(g)))
        ordered_lines: list[Any] = []
        for g in groups:
            # For Arabic names, order tokens right-to-left within the line by x coordinate (desc)
            g_sorted = sorted(g, key=lambda t: t[0], reverse=True)
            ordered_lines.extend([l for _, _, _, l in g_sorted])

        # Build a logical string and infer spaces from inter-token gaps (RTL)
        def _x_bounds(obj: Any) -> tuple[float, float]:
            try:
                xs = [float(p[0]) for p in getattr(obj, "bbox", [])]
                if xs:
                    return (min(xs), max(xs))
            except Exception:
                # Do not mutate field state here; just ignore
                pass
        # BANQUE_MISR cheque number selection is overridden later in run_pipeline_on_image()
        

        # AAIB: rectify rare misread years like 2928 -> 2028 in recognized date strings
        if field == "date" and bank.upper() == "AAIB" and DATE_RX.search(str(text or "")):
            try:
                m_fix = re.search(r"(?i)(\d{1,2})\s*[\/\-\.]?\s*([A-Za-z]{3})\s*[\/\-\.]?\s*(\d{4})", str(text))
                if m_fix and m_fix.group(3).startswith("29"):
                    text = f"{m_fix.group(1)}/{m_fix.group(2)}/20{m_fix.group(3)[2:]}"
            except Exception:
                pass

        

        texts: list[str] = []
        for l in ordered_lines:
            raw_t = str(getattr(l, "text", "")).strip()
            if not raw_t:
                continue
            # Use tokens as-is; rely on RTL token ordering and fix_arabic_text for shaping
            texts.append(raw_t)
        bounds: list[tuple[float, float]] = [_x_bounds(l) for l in ordered_lines if str(getattr(l, "text", "")).strip()]
        widths: list[float] = [(b[1] - b[0]) for b in bounds if (b[1] - b[0]) > 0]
        # Median width for robustness
        avg_w: float = (sorted(widths)[len(widths)//2] if widths else 0.0)
        if avg_w <= 0:
            avg_w = 1.0
        # Compute inter-token gaps (RTL ordering): prev_left - curr_right
        gaps: list[float] = []
        for i in range(1, len(bounds)):
            prev_b = bounds[i - 1]
            curr_b = bounds[i]
            gaps.append(prev_b[0] - curr_b[1])
        med_gap: float = (sorted(gaps)[len(gaps)//2] if gaps else 0.0)
        # Decide threshold: larger of (0.5*avg_w) and (1.5*med_gap)
        thr = max(0.5 * avg_w, 1.5 * med_gap)
        pieces: list[str] = []
        last_idx = -1
        for idx, (t, b) in enumerate(zip(texts, bounds)):
            if not t:
                continue
            if pieces and last_idx >= 0:
                prev_b = bounds[last_idx]
                gap = prev_b[0] - b[1]
                if gap > thr:
                    pieces.append(" ")
            pieces.append(t)
            last_idx = idx
        joined = "".join(pieces) if pieces else ""
        joined = fix_arabic_text(joined, for_display=False)
        # Clean payee text: remove leading label phrases, branch words, and Latin noise
        try:
            # Remove everything up to and including Arabic 'to' keywords
            joined = re.sub(r"^.*?(?:\bالى\b|\bالي\b|\bإلى\b)", "", joined)
            # Drop Latin letters and stray punctuation
            joined = re.sub(r"[A-Za-z]+", "", joined)
            joined = re.sub(r'[!"\'`~^_=<>\[\]{}|\\]', " ", joined)
            # Remove Arabic 'branch' word and following token
            joined = re.sub(r"فرع\s*\S+", "", joined)
            joined = re.sub(r"\s+", " ", joined).strip()
        except Exception:
            pass
        avg_conf = float(sum(float(getattr(l, "confidence", 0.0)) for l in ordered_lines) / max(1, len(ordered_lines)))
        return joined, avg_conf, "ar"
    text, conf, lang = _select_best_text(field, lines)
    if field == "date" and not DATE_RX.search(text or ""):
        bx1, by1, bx2, by2 = bbox
        # Expand ROI more aggressively for date to accommodate small fonts
        exp = int(0.12 * w)
        nb = (
            max(0, bx1 - exp),
            max(0, by1 - int(0.04 * h)),
            min(w - 1, bx2 + exp),
            min(h - 1, by2 + int(0.04 * h)),
        )
        lines2 = engine.ocr_roi(img, roi=nb, languages=langs, min_confidence=min_conf, padding=6, n_votes=2, max_width=roi_max_w)
        if lines2:
            t2, c2, l2 = _select_best_text(field, lines2)
            if DATE_RX.search(t2 or "") and c2 >= conf:
                return t2, c2, l2
    if field == "amount_numeric" and (not AMOUNT_DEC_RX.search(text or "")):
        bx1, by1, bx2, by2 = bbox
        exp = int(0.06 * w)
        nb = (bx1, by1, min(w - 1, bx2 + exp), by2)
        lines2 = engine.ocr_roi(img, roi=nb, languages=langs, min_confidence=min_conf, padding=6, n_votes=2, max_width=roi_max_w)
        if lines2:
            t2, c2, l2 = _select_best_text(field, lines2)
            if AMOUNT_DEC_RX.search(t2 or "") and c2 >= conf:
                return t2, c2, l2
    if field == "date" and not DATE_RX.search(text or ""):
        return "", 0.0, ""
    if field == "amount_numeric" and not (AMOUNT_DEC_RX.search(text or "") or AMOUNT_RX.search(text or "")):
        return "", 0.0, ""
    return text, conf, lang


def run_pipeline_on_image(image_path: str, bank: str, template_id: str = "auto", *, langs: List[str] | None = None, min_conf: float = 0.3) -> Dict[str, Dict[str, Any]]:
    """Run full OCR+locator+ROI OCR pipeline on a single image, return fields mapping.

    Returns mapping field -> record compatible with audit JSON expected by UI.
    """
    if langs is None:
        langs = ["en"] if MUTE_NAME else ["en", "ar"]
    prof = get_current_profiler()
    if prof is not None:
        prof.add_meta(bank=bank, image=os.path.basename(image_path))
    if prof is not None:
        with prof.span("load_image"):
            img = _load_image(image_path)
    else:
        img = _load_image(image_path)
    # Bank-specific full-image downscale override: OCR_MAX_WIDTH_<BANK>
    try:
        _dw_env = os.getenv(f"OCR_MAX_WIDTH_{bank.upper()}")
        down_w = int(_dw_env) if _dw_env is not None else None
    except Exception:
        down_w = None
    if down_w is None:
        down_w = None  # use global default in _maybe_downscale
    if prof is not None:
        with prof.span("downscale"):
            img = _maybe_downscale(img, max_width=down_w)
    else:
        img = _maybe_downscale(img, max_width=down_w)
    h, w_img = img.shape[:2]
    if prof is not None:
        with prof.span("get_engine"):
            engine = _get_engine()
    else:
        engine = _get_engine()
    # Precompute some global OCR lines
    if prof is not None:
        with prof.span("ocr_full_en"):
            full_lines_en = engine.ocr_image(img, languages=["en"], min_confidence=min_conf)
    else:
        full_lines_en = engine.ocr_image(img, languages=["en"], min_confidence=min_conf)
    no_lines = [l for l in full_lines_en if LABEL_NO_RX.search(str(l.text))]
    # Avoid redundant second full-image OCR; if Arabic is needed, run it separately and concatenate
    if set(langs) == {"en"} or (MUTE_NAME and set(langs) == {"en"}):
        full_lines = full_lines_en
    elif "ar" in langs:
        if prof is not None:
            with prof.span("ocr_full_ar"):
                full_lines_ar = engine.ocr_image(img, languages=["ar"], min_confidence=min_conf)
        else:
            full_lines_ar = engine.ocr_image(img, languages=["ar"], min_confidence=min_conf)
        # Concatenate preserving order (English then Arabic)
        full_lines = list(full_lines_en) + list(full_lines_ar)
    else:
        # Uncommon case: languages excludes 'en'
        if prof is not None:
            with prof.span("ocr_full_other", langs="+".join(langs)):
                full_lines = engine.ocr_image(img, languages=langs, min_confidence=min_conf)
        else:
            full_lines = engine.ocr_image(img, languages=langs, min_confidence=min_conf)
    # Persist raw OCR lines for debugging/inspection
    try:
        if os.getenv("WRITE_OCR_LINES", "0") == "1":
            _write_raw_ocr_lines(bank, image_path, full_lines)
    except Exception:
        pass
    loc_lines = _ocr_lines_for_locator(full_lines)
    if prof is not None:
        with prof.span("locate_fields"):
            loc = locate_fields(image_shape=(h, w_img), bank_id=bank, template_id=template_id, ocr_lines=loc_lines)
    else:
        loc = locate_fields(image_shape=(h, w_img), bank_id=bank, template_id=template_id, ocr_lines=loc_lines)

    # BANQUE_MISR/CIB: preselect cheque number from full-image anchors band (between 'Cheque' and 'شيك')
    en_cheq = None
    ar_cheq = None
    if bank.upper() in ("BANQUE_MISR", "CIB"):
        try:
            # Find best English 'Cheque' occurrence near top
            cand_en = [l for l in full_lines_en if re.search(r"(?i)\bcheque\b", str(l.text))]
            if cand_en:
                en_cheq = max(cand_en, key=lambda l: float(getattr(l, "confidence", 0.0)))
            # Find Arabic 'شيك'
            cand_ar = [l for l in full_lines if re.search(r"شيك", str(l.text))]
            if cand_ar:
                ar_cheq = max(cand_ar, key=lambda l: float(getattr(l, "confidence", 0.0)))
        except Exception:
            pass

    fields: Dict[str, Dict[str, Any]] = {}
    for field, rec in loc.items():
        bx1, by1, bx2, by2 = tuple(int(x) for x in rec.get("bbox", [0, 0, 0, 0]))
        if field == "cheque_number":
            expand = int(0.12 * w_img)
            bx2 = min(w_img - 1, bx2 + expand)
        bbox = (bx1, by1, bx2, by2)
        if field == "bank_name":
            text, ocr_conf, ocr_lang = bank, 1.0, "en"
        else:
            # Reuse full-image English lines inside ROI first; fallback to ROI OCR only if needed
            text, ocr_conf, ocr_lang = _best_text_from_roi(engine, img, bbox, field, min_conf, full_lines=full_lines_en)
        selected_src: Optional[str] = None
        # BANQUE_MISR: override cheque number selection with strict top-band numeric pick
        if field == "cheque_number" and bank.upper() == "BANQUE_MISR":
            try:
                # Ignore any generic preselect for this field — start clean
                text = ""
                ocr_conf = 0.0
                ocr_lang = ""
                # Strict filters
                def _micr_like_line(s: str) -> bool:
                    if re.search(r'[\:"]', s):
                        return True
                    blob = re.sub(r"\D", "", s)
                    return len(blob) >= 12
                def _isolated(tok: str, s: str) -> bool:
                    # Allow small leftover digit noise but reject additional long numbers
                    rem = re.sub(re.escape(tok), "", s, count=1)
                    nums = re.findall(r"\d+", rem)
                    if not nums:
                        return True
                    if any(len(g) >= 6 for g in nums):
                        return False
                    total = sum(len(g) for g in nums)
                    return total <= 6
                # Amount-related exclusions: skip lines that are visually inside the amount bbox or look like amounts
                amt_bbox = None
                try:
                    arec = loc.get("amount_numeric")
                    if arec and isinstance(arec.get("bbox"), (list, tuple)):
                        ax1, ay1, ax2, ay2 = tuple(int(x) for x in arec["bbox"])  # template-located amount box
                        padx = int(0.06 * w_img)
                        pady = int(0.05 * h)
                        amt_bbox = (
                            max(0, ax1 - padx),
                            max(0, ay1 - pady),
                            min(w_img - 1, ax2 + padx),
                            min(h - 1, ay2 + pady),
                        )
                except Exception:
                    amt_bbox = None
                def _in_amount_zone(l: Any) -> bool:
                    if not amt_bbox:
                        return False
                    try:
                        cx = float(getattr(l, "center", (0.0, 0.0))[0])
                        cy = float(getattr(l, "center", (0.0, 0.0))[1])
                    except Exception:
                        return False
                    x1, y1, x2, y2 = amt_bbox
                    return (x1 <= cx <= x2) and (y1 <= cy <= y2)
                # Build exclusion set from amount zone lines (8-digit substrings found there)
                amt_excl: set[str] = set()
                try:
                    for lz in full_lines_en:
                        if not _in_amount_zone(lz):
                            continue
                        zs = str(getattr(lz, "text", ""))
                        for m in re.finditer(r"(?<!\d)\d{8}(?!\d)", zs):
                            amt_excl.add(m.group(0))
                        # Also consider 8-run inside short digit blob
                        blobz = re.sub(r"\D", "", zs)
                        if 8 <= len(blobz) <= 10:
                            amt_excl.add(blobz[:8])
                except Exception:
                    pass
                def _amount_like_line(s: str) -> bool:
                    # Typical amount formats or currency labeling
                    if re.search(r"(?i)\begp\b|pounds|جنيه", s):
                        return True
                    if "," in s or "." in s:
                        # Presence of thousand separators / decimals
                        if re.search(r"\d[\d,]*\.(\d{2})\b", s) or re.search(r"\b\d{1,3}(?:,\d{3})+\b", s):
                            return True
                    return False
                best_tok = None
                best_line = None
                best_score = -1e9
                # Stage 0: If English 'CHEQUE' label exists, prefer same row to the right, left 68% width
                try:
                    if en_cheq is not None:
                        lx = float(getattr(en_cheq, "center", (0.0, 0.0))[0])
                        ly = float(getattr(en_cheq, "center", (0.0, 0.0))[1])
                        for l in full_lines:
                            s = str(getattr(l, "text", ""))
                            try:
                                cx = float(getattr(l, "center", (0.0, 0.0))[0])
                                cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            except Exception:
                                continue
                            if abs(cy - ly) > 0.08 * h or cx < lx or cx >= 0.68 * w_img:
                                continue
                            if _micr_like_line(s) or _amount_like_line(s) or _in_amount_zone(l):
                                continue
                            for m in re.finditer(r"(?<!\d)\d{8}(?!\d)", s):
                                tok = m.group(0)
                                if not _isolated(tok, s):
                                    continue
                                c = float(getattr(l, "confidence", 0.0))
                                sc = c - 0.10 * abs(cx - lx) / max(1.0, 0.5 * w_img)
                                if sc > best_score:
                                    best_score = sc
                                    best_tok = tok
                                    best_line = l
                                    picked_src = "bm_label_row"
                    # Stage 0b: If Arabic 'شيك' label exists, prefer same row to the left of it, still left of 78% width
                    if best_tok is None and ar_cheq is not None:
                        ax = float(getattr(ar_cheq, "center", (0.0, 0.0))[0])
                        ay = float(getattr(ar_cheq, "center", (0.0, 0.0))[1])
                        for l in full_lines:
                            s = str(getattr(l, "text", ""))
                            try:
                                cx = float(getattr(l, "center", (0.0, 0.0))[0])
                                cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            except Exception:
                                continue
                            if abs(cy - ay) > 0.08 * h or cx > ax or cx >= 0.78 * w_img:
                                continue
                            if _micr_like_line(s) or _amount_like_line(s) or _in_amount_zone(l):
                                continue
                            for m in re.finditer(r"(?<!\d)\d{8}(?!\d)", s):
                                tok = m.group(0)
                                if not _isolated(tok, s):
                                    continue
                                c = float(getattr(l, "confidence", 0.0))
                                sc = c - 0.10 * abs(cx - ax) / max(1.0, 0.5 * w_img)
                                if sc > best_score:
                                    best_score = sc
                                    best_tok = tok
                                    best_line = l
                                    picked_src = "bm_label_row_ar"
                except Exception:
                    pass
                # Stage A: Prefer mid-top band [30%..55%] of image height (where BM tokens consistently sit)
                y1 = 0.30 * h
                y2 = 0.55 * h
                picked_src = None
                def _join_4x4(s: str) -> str | None:
                    m = re.search(r"(?<!\d)(\d{4})\D{1,3}(\d{4})(?!\d)", s)
                    if not m:
                        return None
                    tok = m.group(1) + m.group(2)
                    return tok if _isolated(tok, s) else None
                for l in full_lines:
                    s = str(getattr(l, "text", ""))
                    try:
                        cy = float(getattr(l, "center", (0.0, 0.0))[1])
                        cx = float(getattr(l, "center", (0.0, 0.0))[0])
                    except Exception:
                        continue
                    if not (y1 <= cy <= y2):
                        continue
                    # Avoid right-most area (amount lives on far right for BM) and amount-like lines/zone
                    if cx >= 0.78 * w_img:
                        continue
                    if _micr_like_line(s) or _amount_like_line(s) or _in_amount_zone(l):
                        continue
                    for m in re.finditer(r"(?<!\d)\d{8}(?!\d)", s):
                        tok = m.group(0)
                        if not _isolated(tok, s):
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        if c > best_score:
                            best_score = c
                            best_tok = tok
                            best_line = l
                            picked_src = "bm_fullband_mid"
                    # Safe 4x4 join fallback for this line
                    if best_tok is None:
                        j = _join_4x4(s)
                        if j:
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best_score:
                                best_score = c
                                best_tok = j
                                best_line = l
                                picked_src = "bm_fullband_mid_join"
                # Stage B: If none found in mid band, widen to broad top band [1%..60%]
                if best_tok is None:
                    y1b = 0.01 * h
                    y2b = 0.60 * h
                    for l in full_lines:
                        s = str(getattr(l, "text", ""))
                        try:
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            cx = float(getattr(l, "center", (0.0, 0.0))[0])
                        except Exception:
                            continue
                        if not (y1b <= cy <= y2b):
                            continue
                        if cx >= 0.78 * w_img:
                            continue
                        if _micr_like_line(s) or _amount_like_line(s) or _in_amount_zone(l):
                            continue
                        for m in re.finditer(r"(?<!\d)\d{8}(?!\d)", s):
                            tok = m.group(0)
                            if not _isolated(tok, s):
                                continue
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best_score:
                                best_score = c
                                best_tok = tok
                                best_line = l
                                picked_src = "bm_fullband"
                        if best_tok is None:
                            j = _join_4x4(s)
                            if j:
                                c = float(getattr(l, "confidence", 0.0))
                                if c > best_score:
                                    best_score = c
                                    best_tok = j
                                    best_line = l
                                    picked_src = "bm_fullband_join"
                # Stage C: If still none, ROI OCR a broad mid-top band to recover misses
                if best_tok is None:
                    band_bbox = (
                        int(0.05 * w_img),
                        int(0.20 * h),
                        int(0.78 * w_img),  # restrict to left 78% to avoid amount region
                        int(0.65 * h),
                    )
                    try:
                        roi_lines = engine.ocr_roi(
                            img,
                            roi=band_bbox,
                            languages=(["en", "ar"] if "ar" in langs else ["en"]),
                            min_confidence=min_conf,
                            padding=6,
                            n_votes=2,
                        ) or []
                    except Exception:
                        roi_lines = []
                    for l in roi_lines:
                        s = str(getattr(l, "text", ""))
                        if _micr_like_line(s) or _amount_like_line(s):
                            continue
                        # First try boundary exact 8
                        got = None
                        m8 = re.search(r"(?<!\d)\d{8}(?!\d)", s)
                        if m8:
                            tok = m8.group(0)
                            if _isolated(tok, s):
                                got = tok
                        if got:
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best_score:
                                best_score = c
                                best_tok = got
                                best_line = l
                                picked_src = "bm_band_roi"
                # Stage D: last resort — global 8-digit sweep across all lines with strict filters
                if best_tok is None:
                    for l in full_lines:
                        s = str(getattr(l, "text", ""))
                        try:
                            cx = float(getattr(l, "center", (0.0, 0.0))[0])
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                        except Exception:
                            continue
                        # Avoid amount zone and MICR-like or amount-like lines
                        if _in_amount_zone(l) or _micr_like_line(s) or _amount_like_line(s):
                            continue
                        # Slight right guard to avoid amount column
                        if cx >= 0.90 * w_img:
                            continue
                        m8 = re.search(r"(?<!\d)\d{8}(?!\d)", s)
                        if not m8:
                            continue
                        tok = m8.group(0)
                        if not _isolated(tok, s):
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        if c > best_score:
                            best_score = c
                            best_tok = tok
                            best_line = l
                            picked_src = "bm_global_8"
                if best_tok is not None:
                    text = best_tok
                    ocr_conf = max(float(ocr_conf), float(getattr(best_line, "confidence", 0.0)))
                    ocr_lang = "en"
                    selected_src = picked_src or "bm_fullband"
                    # Override bbox to the selected line for audit clarity
                    try:
                        pts = getattr(best_line, "bbox", None)
                        if pts:
                            xs = [int(p[0]) for p in pts]
                            ys = [int(p[1]) for p in pts]
                            bx1 = max(0, min(xs) - int(0.02 * w_img))
                            by1 = max(0, min(ys) - int(0.02 * h))
                            bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                            by2 = min(h - 1, max(ys) + int(0.02 * h))
                            bbox = (bx1, by1, bx2, by2)
                    except Exception:
                        pass
                else:
                    # Stage C2: fallback to template ROI OCR (field bbox) with same strict filters
                    try:
                        roi_lines2 = engine.ocr_roi(
                            img,
                            roi=(bx1, by1, bx2, by2),
                            languages=(["en", "ar"] if "ar" in langs else ["en"]),
                            min_confidence=min_conf,
                            padding=6,
                            n_votes=2,
                        ) or []
                        best2 = None
                        best2_c = -1e9
                        for l in roi_lines2:
                            s = str(getattr(l, "text", ""))
                            if _micr_like_line(s) or _amount_like_line(s) or _in_amount_zone(l):
                                continue
                            m8 = re.search(r"(?<!\d)\d{8}(?!\d)", s)
                            if not m8:
                                continue
                            tok = m8.group(0)
                            if tok in amt_excl or not _isolated(tok, s):
                                continue
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best2_c:
                                best2_c = c
                                best2 = (tok, l)
                        if best2 is not None:
                            text = best2[0]
                            ocr_conf = max(float(ocr_conf), float(getattr(best2[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = "bm_roi_template"
                            try:
                                pts = getattr(best2[1], "bbox", None)
                                if pts:
                                    xs = [int(p[0]) for p in pts]
                                    ys = [int(p[1]) for p in pts]
                                    bx1 = max(0, min(xs) - int(0.02 * w_img))
                                    by1 = max(0, min(ys) - int(0.02 * h))
                                    bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                                    by2 = min(h - 1, max(ys) + int(0.02 * h))
                                    bbox = (bx1, by1, bx2, by2)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass
        # NBE: Cheque number — preselect 14-digit token near 'CHEQUE' on full image (with MICR guard and 7x7 join)
        if field == "cheque_number" and bank.upper() == "NBE":
            try:
                # Find English 'CHEQUE' near the top
                label_lines = [l for l in full_lines_en if re.search(r"(?i)\bcheque\b", str(l.text))]
                best_tok = None
                best_s = -1e9
                if label_lines:
                    # Build a horizontal band to the right of the leftmost CHEQUE and prefer the same row (label y)
                    lx = min(float(getattr(l, "center", (0.0, 0.0))[0]) for l in label_lines)
                    ly = min(float(getattr(l, "center", (0.0, 0.0))[1]) for l in label_lines)
                    x_l = lx
                    x_r = min(float(w_img), lx + 0.68 * w_img)
                    def _micr_like(s: str) -> bool:
                        if ":" in s:
                            return True
                        blob = re.sub(r"\D", "", s)
                        return len(blob) >= 16
                    def _join_7x7(s: str) -> str | None:
                        m7 = re.search(r"(?<!\d)(\d{7})\D{1,3}(\d{7})(?!\d)", s)
                        return (m7.group(1) + m7.group(2)) if m7 else None
                    for l in full_lines_en:
                        cx = float(getattr(l, "center", (0.0, 0.0))[0])
                        cy = float(getattr(l, "center", (0.0, 0.0))[1])
                        if not (x_l <= cx <= x_r):
                            continue
                        s = str(l.text)
                        if re.search(r"[A-Za-z]", s) or _micr_like(s):
                            continue
                        tok = None
                        m = re.search(r"(?<!\d)\d{14}(?!\d)", s)
                        if m:
                            tok = m.group(0)
                            penalty = 0.0
                        else:
                            j = _join_7x7(s)
                            if j:
                                tok = j
                                penalty = 0.10
                        if not tok:
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        # Prefer the same row as the CHEQUE label (vertical closeness) and to the right of the label (horizontal closeness)
                        hdist = abs(cx - lx) / max(1.0, 0.5 * w_img)
                        vdist = abs(cy - ly) / max(1.0, 0.06 * h)
                        s_score = c - 0.25 * hdist - 0.35 * vdist - penalty
                        if s_score > best_s:
                            best_s = s_score
                            best_tok = (tok, l)
                if best_tok is not None:
                    text = best_tok[0]
                    ocr_conf = max(float(ocr_conf), float(getattr(best_tok[1], "confidence", 0.0)))
                    ocr_lang = "en"
                    selected_src = "nbe_preselect_cheque"
                    # Override bbox to the selected line
                    try:
                        pts = getattr(best_tok[1], "bbox", None)
                        if pts:
                            xs = [int(p[0]) for p in pts]
                            ys = [int(p[1]) for p in pts]
                            bx1 = max(0, min(xs) - int(0.02 * w_img))
                            by1 = max(0, min(ys) - int(0.02 * h))
                            bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                            by2 = min(h - 1, max(ys) + int(0.02 * h))
                            bbox = (bx1, by1, bx2, by2)
                    except Exception:
                        pass
            except Exception:
                pass
        # NBE: Cheque number ROI rescan to boost confidence or recover (14-digit exact, then 7x7 join)
        if field == "cheque_number" and bank.upper() == "NBE" and not re.fullmatch(r"\d{14}", str(text or "")):
            try:
                roi_lines = engine.ocr_roi(
                    img,
                    roi=bbox,
                    languages=["en"],
                    min_confidence=min_conf,
                    padding=6,
                    n_votes=3,
                )
                cx_roi = 0.5 * (bbox[0] + bbox[2])
                def _score_nbe(tok: str, line_obj: Any) -> float:
                    c = float(getattr(line_obj, "confidence", 0.0))
                    try:
                        cx = float(getattr(line_obj, "center", (cx_roi, 0.0))[0])
                        cy = float(getattr(line_obj, "center", (0.0, 0.0))[1])
                    except Exception:
                        cx = cx_roi
                        cy = 0.0
                    dist = abs(cx - cx_roi) / max(1.0, 0.5 * (bbox[2] - bbox[0]))
                    vdist = abs(cy - 0.5 * (bbox[1] + bbox[3])) / max(1.0, 0.25 * max(1, (bbox[3] - bbox[1])))
                    return c - 0.3 * dist - 0.2 * vdist
                best_tok = None
                best_sc = -1e9
                for l in roi_lines or []:
                    s = str(l.text)
                    m = re.search(r"(?<!\d)\d{14}(?!\d)", s)
                    if m:
                        tok = m.group(0)
                        sc = _score_nbe(tok, l)
                        if sc > best_sc:
                            best_sc = sc
                            best_tok = (tok, float(getattr(l, "confidence", 0.0)))
                if best_tok is None:
                    for l in roi_lines or []:
                        s = str(l.text)
                        m7 = re.search(r"(?<!\d)(\d{7})\D{1,3}(\d{7})(?!\d)", s)
                        if m7:
                            tok = m7.group(1) + m7.group(2)
                            sc = _score_nbe(tok, l) - 0.10
                            if sc > best_sc:
                                best_sc = sc
                                best_tok = (tok, float(getattr(l, "confidence", 0.0)))
                if best_tok is not None:
                    text = best_tok[0]
                    ocr_conf = max(float(ocr_conf), float(best_tok[1]))
                    ocr_lang = "en"
                    selected_src = selected_src or "nbe_roi_rescan"
            except Exception:
                pass
        # NBE: Final enforcement — pick best 14-digit on full image if exists (skip MICR-like)
        if field == "cheque_number" and bank.upper() == "NBE":
            try:
                best_tok = None
                best_line = None
                best_s = -1e9
                def _micr_like2(s: str) -> bool:
                    if ":" in s:
                        return True
                    blob = re.sub(r"\D", "", s)
                    return len(blob) >= 16
                for l in full_lines_en:
                    s = str(l.text)
                    if _micr_like2(s):
                        continue
                    m = re.search(r"(?<!\d)\d{14}(?!\d)", s)
                    if not m:
                        # try 7x7 join
                        j = re.search(r"(?<!\d)(\d{7})\D{1,3}(\d{7})(?!\d)", s)
                        if not j:
                            continue
                        tok = j.group(1) + j.group(2)
                        penalty = 0.10
                    else:
                        tok = m.group(0)
                        penalty = 0.0
                    c = float(getattr(l, "confidence", 0.0))
                    sc = c - penalty
                    if sc > best_s:
                        best_s = sc
                        best_tok = tok
                        best_line = l
                if best_tok is not None:
                    text = best_tok
                    ocr_conf = max(float(ocr_conf), float(getattr(best_line, "confidence", 0.0)))
                    ocr_lang = "en"
                    selected_src = selected_src or "nbe_final_full_image"
                    try:
                        pts = getattr(best_line, "bbox", None)
                        if pts:
                            xs = [int(p[0]) for p in pts]
                            ys = [int(p[1]) for p in pts]
                            bx1 = max(0, min(xs) - int(0.02 * w_img))
                            by1 = max(0, min(ys) - int(0.02 * h))
                            bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                            by2 = min(h - 1, max(ys) + int(0.02 * h))
                            bbox = (bx1, by1, bx2, by2)
                    except Exception:
                        pass
            except Exception:
                pass
        # AAIB: Cheque number — prefer full-image heuristics first; heavy ROI rescans gated
        if field == "cheque_number" and bank.upper() == "AAIB":
            try:
                # 1) Full-image search near 'Cheque No.' and in top-left band
                label_lines = [l for l in full_lines_en if re.search(r"(?i)\bcheque\s*no\.?\b", str(l.text))]
                best = None
                best_s = -1e9
                for l in full_lines_en:
                    s = str(l.text)
                    # Skip lines that ARE the label text themselves or common misreads
                    if re.search(r"(?i)(cheque\s*no\.?|cheaue\s*no\.?)$", s.strip()):
                        continue
                    # Skip common misread patterns like "909006500", "909004500", "190900500", etc.
                    # These are often repeated across many cheques and are false positives
                    # Also skip patterns like "005700606", "455990776", "185599046", "095990746", "690972776"
                    if re.fullmatch(r"(909006500|909004500|909001500|190900500|909000500|005700606|455990776|185599046|095990746|690972776|020100175|1909006500)", s.strip()):
                        continue
                    # Skip MICR-like patterns: very long digit blobs or colon-containing lines
                    if ":" in s or len(re.sub(r"\D", "", s)) >= 16:
                        continue
                    mm = list(re.finditer(r"(?<!\d)\d{9}(?!\d)", s))
                    if not mm:
                        continue
                    cx = float(getattr(l, "center", (0.0, 0.0))[0])
                    cy = float(getattr(l, "center", (0.0, 0.0))[1])
                    # Prefer top-left band
                    top_bonus = 0.2 if cy <= 0.22 * h else 0.0
                    left_bonus = 0.15 if cx <= 0.55 * w_img else 0.0
                    c = float(getattr(l, "confidence", 0.0))
                    # Proximity to a 'Cheque No.' label (same row-ish, label to the left)
                    near_label = 0.0
                    for lab in label_lines:
                        ly = float(getattr(lab, "center", (0.0, 0.0))[1])
                        lx = float(getattr(lab, "center", (0.0, 0.0))[0])
                        if abs(ly - cy) <= 0.05 * h and lx <= cx:
                            near_label = 0.2
                            break
                    # Prefer numbers starting with 944 (common AAIB pattern)
                    pattern_bonus = 0.0
                    for m in mm:
                        if m.group(0).startswith(('944', '943', '945', '942')):
                            pattern_bonus = 0.3
                            break
                    score = c + top_bonus + left_bonus + near_label + pattern_bonus
                    if score > best_s:
                        best_s = score
                        # choose first boundary token in the line
                        best = (mm[0].group(0), l)
                if best is not None:
                    text = best[0]
                    ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                    ocr_lang = "en"
                    selected_src = selected_src or "aaib_fullimage"
                    # Override bbox to selected line
                    try:
                        pts = getattr(best[1], "bbox", None)
                        if pts:
                            xs = [int(p[0]) for p in pts]
                            ys = [int(p[1]) for p in pts]
                            bx1 = max(0, min(xs) - int(0.02 * w_img))
                            by1 = max(0, min(ys) - int(0.02 * h))
                            bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                            by2 = min(h - 1, max(ys) + int(0.02 * h))
                            bbox = (bx1, by1, bx2, by2)
                    except Exception:
                        pass
                # 2) If still not valid and heavy fallbacks enabled, ROI re-scan for 9 digits
                if (
                    not re.fullmatch(r"\d{9}", str(text or ""))
                    and (os.getenv("ROI_HEAVY_FALLBACKS_AAIB", "0") == "1" or os.getenv("ROI_HEAVY_FALLBACKS", "0") == "1")
                ):
                    try:
                        cx_roi = 0.5 * (bbox[0] + bbox[2])
                        # ROI downscale width from env
                        try:
                            _roi_mwb = os.getenv(f"ROI_MAX_WIDTH_{bank.upper()}")
                            _roi_mw = int(_roi_mwb) if _roi_mwb else int(os.getenv("ROI_MAX_WIDTH", "0"))
                            roi_max_w: Optional[int] = _roi_mw if _roi_mw > 0 else None
                        except Exception:
                            roi_max_w = None
                        roi_lines = engine.ocr_roi(
                            img,
                            roi=bbox,
                            languages=["en"],
                            min_confidence=min_conf,
                            padding=6,
                            n_votes=3,
                            max_width=roi_max_w,
                        )
                        def aaib_score(tok: str, line_obj: Any) -> float:
                            c = float(getattr(line_obj, "confidence", 0.0))
                            try:
                                cx = float(getattr(line_obj, "center", (cx_roi, 0.0))[0])
                                cy = float(getattr(line_obj, "center", (0.0, 0.0))[1])
                            except Exception:
                                cx = cx_roi
                                cy = 0.0
                            # Prefer tokens near ROI center; avoid long distance
                            dist = abs(cx - cx_roi) / max(1.0, 0.5 * (bbox[2] - bbox[0]))
                            vdist = abs(cy - 0.5 * (bbox[1] + bbox[3])) / max(1.0, 0.25 * (bbox[3] - bbox[1] or 1))
                            return c - 0.35 * dist - 0.2 * vdist
                        best_tok = None
                        best_score = -1e9
                        for l in roi_lines or []:
                            s = str(l.text)
                            # Skip common misread patterns in ROI too
                            if re.fullmatch(r"(909006500|909004500|909001500|190900500|909000500|005700606|455990776|185599046|095990746|690972776|020100175|1909006500)", s.strip()):
                                continue
                            # Skip MICR-like patterns
                            if ":" in s or len(re.sub(r"\D", "", s)) >= 16:
                                continue
                            for m in re.finditer(r"(?<!\d)\d{9}(?!\d)", s):
                                tok = m.group(0)
                                # Additional validation: AAIB cheque numbers typically start with 944
                                if not tok.startswith(('944', '943', '945', '942')):
                                    continue
                                sc = aaib_score(tok, l)
                                if sc > best_score:
                                    best_score = sc
                                    best_tok = (tok, float(getattr(l, "confidence", 0.0)))
                        if best_tok is not None:
                            text = best_tok[0]
                            ocr_conf = max(float(ocr_conf), float(best_tok[1]))
                            ocr_lang = "en"
                            selected_src = selected_src or "aaib_roi_rescan"
                        # 3) As last resort (gated), multi‑line ROI join (n_votes=5)
                        if not re.fullmatch(r"\d{9}", str(text or "")):
                            roi_lines2 = engine.ocr_roi(
                                img,
                                roi=bbox,
                                languages=["en"],
                                min_confidence=min_conf,
                                padding=10,
                                n_votes=5,
                                max_width=roi_max_w,
                            )
                            joined = " ".join([str(getattr(l, "text", "")) for l in (roi_lines2 or [])])
                            m = re.search(r"(?<!\d)\d{9}(?!\d)", joined)
                            if m:
                                text = m.group(0)
                                selected_src = selected_src or "aaib_roi_join"
                    except Exception:
                        pass
            except Exception:
                pass

        # AAIB: Date fallback — prefer full-image region/label/global first; heavy ROI rescan gated
        if field == "date" and bank.upper() == "AAIB" and not DATE_RX.search(str(text or "")):
            try:
                # 1) Search full image top-right band for any date (scan all OCR lines)
                if not DATE_RX.search(str(text or "")):
                    best = None
                    best_c = -1.0
                    for l in full_lines:
                        cx = float(getattr(l, "center", (0.0, 0.0))[0])
                        cy = float(getattr(l, "center", (0.0, 0.0))[1])
                        # Broaden region further: right half of width, rows roughly 4%–40% height
                        if cx < 0.50 * w_img or cy < 0.04 * h or cy > 0.40 * h:
                            continue
                        s = str(l.text)
                        m = DATE_RX.search(s)
                        if not m:
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        if c > best_c:
                            best_c = c
                            best = (m.group(0), l)
                    if best is not None:
                        text = correct_aaib_date_text(best[0])
                        ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                        ocr_lang = "en"
                        selected_src = selected_src or "aaib_date_region"
                # 2) If still missing, use 'Date' label proximity: pick a date to the right on the same row (scan all OCR lines)
                if not DATE_RX.search(str(text or "")):
                    try:
                        labels = [l for l in full_lines if re.search(r"(?i)\bdate\b", str(l.text))]
                        best = None
                        best_s = -1e9
                        for lab in labels:
                            ly = float(getattr(lab, "center", (0.0, 0.0))[1])
                            lx = float(getattr(lab, "center", (0.0, 0.0))[0])
                            for l in full_lines:
                                s = str(l.text)
                                m = DATE_RX.search(s)
                                if not m:
                                    continue
                                cy = float(getattr(l, "center", (0.0, 0.0))[1])
                                cx = float(getattr(l, "center", (0.0, 0.0))[0])
                                if abs(cy - ly) <= 0.05 * h and cx >= lx:
                                    c = float(getattr(l, "confidence", 0.0))
                                    # prefer closer horizontally to the label
                                    sc = c - 0.15 * abs(cx - lx) / max(1.0, 0.5 * w_img)
                                    if sc > best_s:
                                        best_s = sc
                                        best = (m.group(0), l)
                        if best is not None:
                            text = correct_aaib_date_text(best[0])
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = selected_src or "aaib_date_label"
                    except Exception:
                        pass
                # 3) Final global fallback: any date anywhere on full-image (choose highest conf; scan all OCR lines)
                if not DATE_RX.search(str(text or "")):
                    try:
                        best = None
                        best_c = -1.0
                        for l in full_lines:
                            s = str(l.text)
                            m = DATE_RX.search(s)
                            if not m:
                                continue
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best_c:
                                best_c = c
                                best = (m.group(0), l)
                        if best is not None:
                            text = correct_aaib_date_text(best[0])
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = selected_src or "aaib_date_global"
                    except Exception:
                        pass
                # 4) If still missing and heavy fallbacks enabled, ROI rescan (gated)
                if not DATE_RX.search(str(text or "")) and os.getenv("ROI_HEAVY_FALLBACKS", "0") == "1":
                    try:
                        # get ROI downscale width from env as in _best_text_from_roi
                        try:
                            _roi_mw = int(os.getenv("ROI_MAX_WIDTH", "0"))
                            roi_max_w: Optional[int] = _roi_mw if _roi_mw > 0 else None
                        except Exception:
                            roi_max_w = None
                        roi_lines = engine.ocr_roi(
                            img,
                            roi=bbox,
                            languages=["en"],
                            min_confidence=min_conf,
                            padding=8,
                            n_votes=5,
                            max_width=roi_max_w,
                        )
                        best = None
                        best_c = -1.0
                        for l in roi_lines or []:
                            s = str(l.text)
                            m = DATE_RX.search(s)
                            if not m:
                                continue
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best_c:
                                best_c = c
                                best = (m.group(0), l)
                        if best is not None:
                            text = correct_aaib_date_text(best[0])
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = selected_src or "aaib_date_roi"
                    except Exception:
                        pass
            except Exception:
                pass

        # NBE: Date fallback — similar strategy, tolerant to '0ct'/'0ec' and fix 'lan'/'lul'/'lct'
        if field == "date" and bank.upper() == "NBE" and not DATE_RX.search(str(text or "")):
            try:
                # 1) ROI rescan
                roi_lines = engine.ocr_roi(img, roi=bbox, languages=["en"], min_confidence=min_conf, padding=8, n_votes=5)
                best = None
                best_c = -1.0
                for l in roi_lines or []:
                    s = str(l.text)
                    s2 = correct_nbe_date_text(s)
                    m = DATE_RX.search(s2)
                    if not m:
                        continue
                    c = float(getattr(l, "confidence", 0.0))
                    if c > best_c:
                        best_c = c
                        best = (m.group(0), l)
                if best is not None:
                    text = correct_nbe_date_text(best[0])
                    ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                    ocr_lang = "en"
                    selected_src = selected_src or "nbe_date_roi"
                # 2) Label-guided: pick date to the right of 'DATE'
                if not DATE_RX.search(str(text or "")):
                    labels = [l for l in full_lines_en if re.search(r"(?i)\bdate\b", str(l.text))]
                    best = None
                    best_s = -1e9
                    for lab in labels:
                        ly = float(getattr(lab, "center", (0.0, 0.0))[1])
                        lx = float(getattr(lab, "center", (0.0, 0.0))[0])
                        for l in full_lines:
                            s = str(l.text)
                            s2 = correct_nbe_date_text(s)
                            m = DATE_RX.search(s2)
                            if not m:
                                continue
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            cx = float(getattr(l, "center", (0.0, 0.0))[0])
                            if abs(cy - ly) <= 0.06 * h and cx >= lx:
                                c = float(getattr(l, "confidence", 0.0))
                                sc = c - 0.12 * abs(cx - lx) / max(1.0, 0.5 * w_img)
                                if sc > best_s:
                                    best_s = sc
                                    best = (m.group(0), l)
                    if best is not None:
                        text = correct_nbe_date_text(best[0])
                        ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                        ocr_lang = "en"
                        selected_src = selected_src or "nbe_date_label"
                # 3) Global: any date
                if not DATE_RX.search(str(text or "")):
                    best = None
                    best_c = -1.0
                    for l in full_lines:
                        s = str(l.text)
                        s2 = correct_nbe_date_text(s)
                        m = DATE_RX.search(s2)
                        if not m:
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        if c > best_c:
                            best_c = c
                            best = (m.group(0), l)
                    if best is not None:
                        text = correct_nbe_date_text(best[0])
                        ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                        ocr_lang = "en"
                        selected_src = selected_src or "nbe_date_global"
            except Exception:
                pass

        # NBE: Amount strictness — require decimals to avoid picking day-of-month as amount
        if field == "amount_numeric" and bank.upper() == "NBE":
            if not AMOUNT_DEC_RX.search(str(text or "")):
                # Try ROI rescan once more with wider right expansion
                try:
                    bx1, by1, bx2, by2 = bbox
                    nb = (bx1, by1, min(w_img - 1, bx2 + int(0.10 * w_img)), by2)
                    lines2 = engine.ocr_roi(img, roi=nb, languages=["en"], min_confidence=min_conf, padding=8, n_votes=2)
                    cand = [(str(l.text), float(getattr(l, "confidence", 0.0))) for l in (lines2 or []) if AMOUNT_DEC_RX.search(str(l.text))]
                    if cand:
                        best_t, best_c = max(cand, key=lambda t: t[1])
                        text = best_t
                        ocr_conf = max(float(ocr_conf), best_c)
                        ocr_lang = "en"
                        selected_src = selected_src or "nbe_amount_dec_roi"
                except Exception:
                    pass
                # 2) If still missing, search a right-side band on full image for any decimal amount
                if not AMOUNT_DEC_RX.search(str(text or "")):
                    try:
                        best = None
                        best_s = -1e9
                        for l in full_lines_en:
                            cx = float(getattr(l, "center", (0.0, 0.0))[0])
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            # Prefer right third and mid-height rows (typical amount box)
                            if cx < 0.62 * w_img or cy < 0.22 * h or cy > 0.60 * h:
                                continue
                            s = str(l.text)
                            m = AMOUNT_DEC_RX.search(s)
                            if not m:
                                continue
                            c = float(getattr(l, "confidence", 0.0))
                            # Score: confidence + proximity to right edge and to vertical band center
                            right_pref = (cx - 0.62 * w_img) / max(1.0, 0.38 * w_img)
                            vcenter = 1.0 - abs(cy - 0.40 * h) / max(1.0, 0.20 * h)
                            sc = c + 0.2 * right_pref + 0.1 * vcenter
                            if sc > best_s:
                                best_s = sc
                                best = (m.group(0), l)
                        if best is not None:
                            text = best[0]
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = selected_src or "nbe_amount_dec_band"
                            # tighten bbox around detected amount for potential downstream use
                            try:
                                pts = getattr(best[1], "bbox", None)
                                if pts:
                                    xs = [int(p[0]) for p in pts]
                                    ys = [int(p[1]) for p in pts]
                                    bx1 = max(0, min(xs) - int(0.02 * w_img))
                                    by1 = max(0, min(ys) - int(0.02 * h))
                                    bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                                    by2 = min(h - 1, max(ys) + int(0.02 * h))
                                    bbox = (bx1, by1, bx2, by2)
                            except Exception:
                                pass
                    except Exception:
                        pass
                # 3) Final global fallback: pick any decimal amount from full_lines_en (best confidence)
                if not AMOUNT_DEC_RX.search(str(text or "")):
                    try:
                        best = None
                        best_c = -1.0
                        for l in full_lines_en:
                            s = str(l.text)
                            m = AMOUNT_DEC_RX.search(s)
                            if not m:
                                continue
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best_c:
                                best_c = c
                                best = (m.group(0), l)
                        if best is not None:
                            text = best[0]
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = selected_src or "nbe_amount_dec_global"
                    except Exception:
                        pass
                # If still no decimals, clear the field to avoid false amount
                if not AMOUNT_DEC_RX.search(str(text or "")):
                    text = ""
                    ocr_conf = 0.0
                    ocr_lang = ""

        # FABMISR: Amount — reject MICR contamination (lines with "CAIN", "EGP", or multi-space patterns)
        if field == "amount_numeric" and bank.upper() == "FABMISR":
            try:
                cur_text = str(text or "")
                def _fabmisr_micr_amount(s: str) -> bool:
                    # Reject if contains MICR keywords or patterns like "016 0001"
                    if re.search(r"(?i)(CAIN|EGP|CASH)", s):
                        return True
                    # Reject multi-space separated digit groups (e.g., "00566474 CAIN EGP 016 0001")
                    if re.search(r"\d+\s+[A-Z]+\s+[A-Z]+\s+\d+", s):
                        return True
                    return False
                # If current text is contaminated, search for a clean decimal amount
                if _fabmisr_micr_amount(cur_text) or not AMOUNT_DEC_RX.search(cur_text):
                    best = None
                    best_c = -1.0
                    for l in full_lines_en:
                        s = str(l.text)
                        # Skip MICR-like lines
                        if _fabmisr_micr_amount(s):
                            continue
                        # Look for decimal amounts
                        m = AMOUNT_DEC_RX.search(s)
                        if not m:
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        if c > best_c:
                            best_c = c
                            best = (m.group(0), l)
                    if best is not None:
                        text = best[0]
                        ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                        ocr_lang = "en"
                        selected_src = selected_src or "fabmisr_amount_clean"
            except Exception:
                pass

        # FABMISR: Cheque number — reject MICR noise, prefer "44139XXX" pattern (8 digits)
        if field == "cheque_number" and bank.upper() == "FABMISR":
            try:
                cur_text = str(text or "")
                def _fabmisr_micr_cheque(s: str) -> bool:
                    # Reject MICR patterns: contains colons, or very long digit blobs
                    if ":" in s:
                        return True
                    blob = re.sub(r"\D", "", s)
                    # MICR lines typically have 16+ digits
                    if len(blob) >= 16:
                        return True
                    return False
                # Check if current text is contaminated or doesn't match expected pattern
                is_valid_pattern = re.search(r"(?<!\d)44139\d{3}(?!\d)", cur_text)
                if _fabmisr_micr_cheque(cur_text) or not is_valid_pattern:
                    # Search for 8-digit tokens starting with "44139" (high preference) or any clean 8-digit
                    best = None
                    best_s = -1e9
                    for l in full_lines_en:
                        s = str(l.text)
                        # Skip MICR-like lines and lines with letters
                        if _fabmisr_micr_cheque(s) or re.search(r"[A-Za-z]", s):
                            continue
                        # Prefer 8-digit tokens starting with "44139"
                        m_pref = re.search(r"(?<!\d)(44139\d{3})(?!\d)", s)
                        if m_pref:
                            tok = m_pref.group(1)
                            c = float(getattr(l, "confidence", 0.0))
                            # High score for matching pattern
                            sc = c + 1.0
                            if sc > best_s:
                                best_s = sc
                                best = (tok, l)
                        # Fallback: any 8-digit token
                        elif best is None:
                            m_any = re.search(r"(?<!\d)\d{8}(?!\d)", s)
                            if m_any:
                                tok = m_any.group(0)
                                c = float(getattr(l, "confidence", 0.0))
                                if c > best_s:
                                    best_s = c
                                    best = (tok, l)
                    if best is not None:
                        text = best[0]
                        ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                        ocr_lang = "en"
                        selected_src = selected_src or "fabmisr_cheque_clean"
            except Exception:
                pass

        # NBE: Name fallback — prefer Arabic-only candidate; if full_lines lack Arabic (MUTE_NAME), OCR ROI in Arabic
        if field == "name" and bank.upper() == "NBE":
            try:
                cur = str(text or "")
                def _noisy_nbe(s: str) -> bool:
                    return len(s.strip()) < 3 or bool(re.search(r"[A-Za-z]", s)) or (sum(ch.isdigit() for ch in s) / max(1, len(s)) > 0.2)
                if _noisy_nbe(cur) or re.search(r"فرع", cur):
                    bx1e = max(0, bbox[0] - int(0.02 * w_img))
                    by1e = max(0, bbox[1] - int(0.02 * h))
                    bx2e = min(w_img - 1, bbox[2] + int(0.02 * w_img))
                    by2e = min(h - 1, bbox[3] + int(0.02 * h))
                    best = None
                    best_c = -1.0
                    for l in full_lines:
                        cx = float(getattr(l, "center", (0.0, 0.0))[0])
                        cy = float(getattr(l, "center", (0.0, 0.0))[1])
                        if not (bx1e <= cx <= bx2e and by1e <= cy <= by2e):
                            continue
                        s = str(getattr(l, "text", ""))
                        if re.search(r"[A-Za-z\d]", s):
                            continue
                        if re.search(r"فرع", s):
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        if c > best_c:
                            best_c = c
                            best = (s, l)
                    # If no Arabic text found in precomputed full_lines (likely no 'ar' OCR), OCR ROI in Arabic now
                    if best is None:
                        roi_ar = engine.ocr_roi(img, roi=(bx1e, by1e, bx2e, by2e), languages=["ar"], min_confidence=min_conf, padding=8, n_votes=3)
                        for l in roi_ar or []:
                            s = str(getattr(l, "text", ""))
                            if re.search(r"[A-Za-z\d]", s) or re.search(r"فرع", s):
                                continue
                            c = float(getattr(l, "confidence", 0.0))
                            if c > best_c:
                                best_c = c
                                best = (s, l)
                    if best is not None:
                        clean = best[0]
                        clean = re.sub(r"(?i)\bname\b", "", clean)
                        clean = re.sub(r"بحاسلا\s*مس", "", clean)
                        clean = re.sub(r"فرع\s*\S+", "", clean)
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if clean:
                            text = clean
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "ar"
                            selected_src = selected_src or "nbe_name_roi"
            except Exception:
                pass
            # If still missing/too short, try Arabic label-anchored fallback on full image
            try:
                cur = str(text or "")
                if len(cur.strip()) < 3:
                    labels = [l for l in full_lines if re.search(r"(ادفعوا\s*لأمر|اسم\s*الحساب|بحاسلا\s*مس)", str(l.text))]
                    best = None
                    best_s = -1e9
                    for lab in labels:
                        ly = float(getattr(lab, "center", (0.0, 0.0))[1])
                        lx = float(getattr(lab, "center", (0.0, 0.0))[0])
                        for l in full_lines:
                            s = str(getattr(l, "text", ""))
                            if re.search(r"[A-Za-z\d]", s) or re.search(r"فرع", s):
                                continue
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            cx = float(getattr(l, "center", (0.0, 0.0))[0])
                            if abs(cy - ly) <= 0.06 * h and cx >= lx:
                                c = float(getattr(l, "confidence", 0.0))
                                sc = c - 0.10 * abs(cx - lx) / max(1.0, 0.5 * w_img)
                                if sc > best_s:
                                    best_s = sc
                                    best = (s, l)
                    if best is not None:
                        clean = best[0]
                        clean = re.sub(r"(?i)\bname\b", "", clean)
                        clean = re.sub(r"بحاسلا\s*مس", "", clean)
                        clean = re.sub(r"فرع\s*\S+", "", clean)
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if clean:
                            text = clean
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "ar"
                            selected_src = selected_src or "nbe_name_label"
            except Exception:
                pass

        # AAIB: Name fallback — prefer highest-conf Arabic-only candidate within expanded ROI, drop branch labels
        if field == "name" and bank.upper() == "AAIB":
            try:
                cur = str(text or "")
                def _is_noisy(s: str) -> bool:
                    return len(s.strip()) < 3 or bool(re.search(r"[A-Za-z\d]", s))
                if _is_noisy(cur) or re.search(r"فرع", cur):
                    bx1e = max(0, bbox[0] - int(0.02 * w_img))
                    by1e = max(0, bbox[1] - int(0.02 * h))
                    bx2e = min(w_img - 1, bbox[2] + int(0.02 * w_img))
                    by2e = min(h - 1, bbox[3] + int(0.02 * h))
                    best = None
                    best_c = -1.0
                    for l in full_lines:
                        cx = float(getattr(l, "center", (0.0, 0.0))[0])
                        cy = float(getattr(l, "center", (0.0, 0.0))[1])
                        if not (bx1e <= cx <= bx2e and by1e <= cy <= by2e):
                            continue
                        s = str(getattr(l, "text", ""))
                        if re.search(r"[A-Za-z\d]", s):
                            continue
                        if re.search(r"فرع", s):
                            continue
                        c = float(getattr(l, "confidence", 0.0))
                        if c > best_c:
                            best_c = c
                            best = (s, l)
                    if best is not None:
                        clean = best[0]
                        # Remove common labels/phrases
                        clean = re.sub(r"(?i)\bname\b", "", clean)
                        clean = re.sub(r"بحاسلا\s*مس", "", clean)
                        clean = re.sub(r"فرع\s*\S+", "", clean)
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if clean:
                            text = clean
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "ar"
                            selected_src = selected_src or "aaib_name_fallback"
            except Exception:
                pass
            # If still missing/too short, try Arabic label-anchored fallback on full image
            try:
                cur = str(text or "")
                if len(cur.strip()) < 3:
                    # Find Arabic payee/name labels
                    labels = [l for l in full_lines if re.search(r"(ادفعوا\s*لأمر|اسم\s*الحساب|بحاسلا\s*مس)", str(l.text))]
                    best = None
                    best_s = -1e9
                    for lab in labels:
                        ly = float(getattr(lab, "center", (0.0, 0.0))[1])
                        lx = float(getattr(lab, "center", (0.0, 0.0))[0])
                        for l in full_lines:
                            s = str(getattr(l, "text", ""))
                            # Arabic-only candidate; ignore Latin/digits and ignore branch words
                            if re.search(r"[A-Za-z\d]", s) or re.search(r"فرع", s):
                                continue
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            cx = float(getattr(l, "center", (0.0, 0.0))[0])
                            # Same row tolerance and to the right of the label
                            if abs(cy - ly) <= 0.06 * h and cx >= lx:
                                c = float(getattr(l, "confidence", 0.0))
                                sc = c - 0.10 * abs(cx - lx) / max(1.0, 0.5 * w_img)
                                if sc > best_s:
                                    best_s = sc
                                    best = (s, l)
                    if best is not None:
                        clean = best[0]
                        clean = re.sub(r"(?i)\bname\b", "", clean)
                        clean = re.sub(r"بحاسلا\s*مس", "", clean)
                        clean = re.sub(r"فرع\s*\S+", "", clean)
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if clean:
                            text = clean
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "ar"
                            selected_src = selected_src or "aaib_name_label"
            except Exception:
                pass
        # CIB: Prefer preselected 12-digit token from anchor band on full-image OCR
        preselected_used = False
        preselected_line = None
        if field == "cheque_number" and bank.upper() == "CIB" and (en_cheq is not None or ar_cheq is not None):
            try:
                # Build band horizontally between anchors if both exist, else to the right of English or left of Arabic
                if en_cheq is not None and ar_cheq is not None:
                    ex = float(getattr(en_cheq, "center", (0.0, 0.0))[0])
                    ax = float(getattr(ar_cheq, "center", (w_img, 0.0))[0])
                    x_left, x_right = (ex, ax) if ex < ax else (ax, ex)
                    x_l = max(0.0, x_left + 0.02 * w_img)
                    x_r = min(float(w_img), x_right - 0.02 * w_img)
                elif en_cheq is not None:
                    ex = float(getattr(en_cheq, "center", (0.0, 0.0))[0])
                    x_l, x_r = ex, min(float(w_img), ex + 0.50 * w_img)
                else:  # only Arabic
                    ax = float(getattr(ar_cheq, "center", (w_img, 0.0))[0])
                    x_l, x_r = max(0.0, ax - 0.50 * w_img), ax
                # Preselect across anchors horizontally; prefer vertical ~60% height (soft penalty, no hard Y filter)
                y_pref = 0.60 * h
                best_tok = None
                best_score = -1e9
                cx_band = 0.5 * (x_l + x_r)
                def _score_cib(tok: str, cx: float, cy: float, conf: float) -> float:
                    dist = abs(cx - cx_band) / max(1.0, 0.5 * (x_r - x_l))
                    vdist = abs(cy - y_pref) / max(1.0, 0.25 * h)
                    lz = len(tok) - len(tok.lstrip('0'))
                    # Minimal biasing: slight penalty for many leading zeros
                    return conf - 0.3 * dist - 0.2 * vdist - 0.05 * lz
                def _join_4x4x4(s: str) -> str | None:
                    m = re.search(r"(?<!\d)(\d{4})\D{1,3}(\d{4})\D{1,3}(\d{4})(?!\d)", s)
                    return (m.group(1) + m.group(2) + m.group(3)) if m else None
                def _join_6x6(s: str) -> str | None:
                    m = re.search(r"(?<!\d)(\d{6})\D{1,3}(\d{6})(?!\d)", s)
                    return (m.group(1) + m.group(2)) if m else None
                for l in full_lines:
                    cx = float(getattr(l, "center", (0.0, 0.0))[0])
                    cy = float(getattr(l, "center", (0.0, 0.0))[1])
                    if not (x_l <= cx <= x_r):
                        continue
                    s = str(l.text)
                    # reject if letters/punct or explicit 'No' label lines
                    if re.search(r"[A-Za-z]", s) or re.search(r"[\:\"A-Z]", s) or LABEL_NO_RX.search(s):
                        continue
                    # 1) Exact boundary 12-digit
                    for m in re.finditer(r"(?<!\d)\d{12}(?!\d)", s):
                        tok = m.group(0)
                        c = float(getattr(l, "confidence", 0.0))
                        sc = _score_cib(tok, cx, cy, c)
                        if sc > best_score:
                            best_score = sc
                            best_tok = (tok, c, l)
                    # 2) 12-digit joins as fallback
                    if best_tok is None:
                        j = _join_4x4x4(s) or _join_6x6(s)
                        if j and len(j) == 12:
                            c = float(getattr(l, "confidence", 0.0))
                            sc = _score_cib(j, cx, cy, c) - 0.10
                            if sc > best_score:
                                best_score = sc
                                best_tok = (j, c, l)
                if best_tok is not None:
                    text = best_tok[0]
                    ocr_conf = max(float(ocr_conf), float(best_tok[1]))
                    ocr_lang = "en"
                    preselected_used = True
                    preselected_line = best_tok[2]
                    selected_src = "bm_preselect_band"
            except Exception:
                pass
        # CIB: Re-scan ROI to extract exact 12-digit token with highest confidence
        if field == "cheque_number" and bank.upper() == "CIB" and not preselected_used:
            try:
                roi_lines = engine.ocr_roi(
                    img,
                    roi=bbox,
                    languages=(["en", "ar"] if "ar" in langs else ["en"]),
                    min_confidence=min_conf,
                    padding=6,
                    n_votes=3,
                )
                cx_roi = 0.5 * (bbox[0] + bbox[2])
                def score_tok(tok: str, line_obj: Any) -> float:
                    c = float(getattr(line_obj, "confidence", 0.0))
                    try:
                        cx = float(getattr(line_obj, "center", (cx_roi, 0.0))[0])
                        cy = float(getattr(line_obj, "center", (0.0, 0.0))[1])
                    except Exception:
                        cx = cx_roi
                        cy = 0.0
                    # Prefer tokens near ROI center
                    dist = abs(cx - cx_roi) / max(1.0, 0.5 * (bbox[2] - bbox[0]))
                    vdist = abs(cy - 0.5 * (bbox[1] + bbox[3])) / max(1.0, 0.25 * (bbox[3] - bbox[1] or 1))
                    # Penalize leading zeros
                    lz = len(tok) - len(tok.lstrip('0'))
                    return c - 0.3 * dist - 0.2 * vdist - 0.05 * lz
                best_tok = None
                best_score = -1e9
                # 1) Exact 12-digit tokens with digit boundaries
                for l in roi_lines or []:
                    for m in re.finditer(r"(?<!\d)\d{12}(?!\d)", str(l.text)):
                        tok = m.group(0)
                        s = score_tok(tok, l)
                        if s > best_score:
                            best_score = s
                            best_tok = (tok, float(getattr(l, "confidence", 0.0)))
                # 2) If none, consider 12-digit joins (4x4x4, 6x6)
                if best_tok is None:
                    for l in roi_lines or []:
                        m = re.search(r"(?<!\d)(\d{4})\D{1,3}(\d{4})\D{1,3}(\d{4})(?!\d)", str(l.text))
                        if m:
                            tok = m.group(1) + m.group(2) + m.group(3)
                            s = score_tok(tok, l) - 0.10
                            if s > best_score:
                                best_score = s
                                best_tok = (tok, float(getattr(l, "confidence", 0.0)))
                        m2 = re.search(r"(?<!\d)(\d{6})\D{1,3}(\d{6})(?!\d)", str(l.text))
                        if m2:
                            tok2 = m2.group(1) + m2.group(2)
                            s2 = score_tok(tok2, l) - 0.10
                            if s2 > best_score:
                                best_score = s2
                                best_tok = (tok2, float(getattr(l, "confidence", 0.0)))
                # 3) If still none, consider 13-digit tokens, trimmed to 12 with a penalty
                if best_tok is None:
                    for l in roi_lines or []:
                        for m in re.finditer(r"(?<!\d)\d{13}(?!\d)", str(l.text)):
                            full = m.group(0)
                            tok = full[:12]
                            s = score_tok(tok, l) - 0.20
                            if s > best_score:
                                best_score = s
                                best_tok = (tok, float(getattr(l, "confidence", 0.0)))
                if best_tok is not None:
                    text = best_tok[0]
                    ocr_conf = max(float(ocr_conf), float(best_tok[1]))
                    ocr_lang = "en"
                    selected_src = "bm_roi_rescan"
            except Exception:
                pass
            # If we preselected a line from the full-image band, override bbox to that line's bbox for audit clarity
            if field == "cheque_number" and preselected_used and preselected_line is not None:
                try:
                    pts = getattr(preselected_line, "bbox", None)
                    if pts:
                        xs = [int(p[0]) for p in pts]
                        ys = [int(p[1]) for p in pts]
                        bx1 = max(0, min(xs) - int(0.02 * w_img))
                        by1 = max(0, min(ys) - int(0.02 * h))
                        bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                        by2 = min(h - 1, max(ys) + int(0.02 * h))
                        bbox = (bx1, by1, bx2, by2)
                except Exception:
                    pass
            # Fallback candidate scan only if we still don't have a valid token
            # Skip entirely for BANQUE_MISR; for CIB require exact 12-digit; for others allow 6+ digits
            if field == "cheque_number" and (
                (bank.upper() == "CIB" and not re.search(r"(?<!\\d)\\d{12}(?!\\d)", str(text or ""))) or
                (bank.upper() not in ("BANQUE_MISR", "CIB") and not NUM_RX.search(text or ""))
            ):
                candidates = []
                cy_roi = 0.5 * (by1 + by2)
                cx_roi = 0.5 * (bx1 + bx2)
                for l in full_lines:
                    m = NUM_RX.search(str(l.text))
                    if not m:
                        continue
                    tok = m.group(0)
                    cy = float(l.center[1]) if hasattr(l, 'center') else cy_roi
                    cx = float(l.center[0]) if hasattr(l, 'center') else cx_roi
                    has_no_near = False
                    for nl in no_lines:
                        ny = float(nl.center[1]) if hasattr(nl, 'center') else cy_roi
                        nx = float(nl.center[0]) if hasattr(nl, 'center') else cx_roi
                        # If a 'No' label is horizontally near and roughly aligned vertically, treat as near
                        if abs(ny - cy) <= 0.05 * h and nx - 0.10 * w_img <= cx <= nx + 0.40 * w_img:
                            has_no_near = True
                            break
                    lead_zeros = len(tok) - len(tok.lstrip('0'))
                    candidates.append({
                        "token": tok,
                        "text": str(l.text),
                        "confidence": float(l.confidence),
                        "lang": str(l.lang),
                        "cy": cy,
                        "cx": cx,
                        "has_no": bool(LABEL_NO_RX.search(str(l.text))),
                        "has_no_near": has_no_near,
                        "lead_zeros": lead_zeros,
                    })
                if candidates:
                    # Prefer numbers near the TOP-MIDDLE of the cheque and away from 'No' labels
                    def _score(d: Dict[str, Any]) -> Tuple:
                        y_top_pref = 0 if d["cy"] <= 0.45 * h else 1
                        x_center_dist = abs(d["cx"] - 0.5 * w_img)
                        len_bias = abs(len(d["token"]) - 12)  # prefer 12 digits
                        no_penalty = 1 if (d["has_no"] or d["has_no_near"]) else 0
                        center_penalty = x_center_dist / max(1.0, 0.5 * w_img)
                        return (
                            no_penalty,          # avoid 'No' lines
                            y_top_pref,          # prefer upper half
                            len_bias,            # prefer length ~12
                            center_penalty,      # prefer center x
                            -float(d["confidence"]),
                        )
                    best = sorted(candidates, key=_score)[0]
                    text, ocr_conf, ocr_lang = best["token"], best["confidence"], best["lang"]
                    selected_src = selected_src or "fallback_candidates"
            # Final enforcement: For CIB, if a clean 12-digit exists in full-image OCR, take the best
            if field == "cheque_number" and bank.upper() == "CIB":
                try:
                    best_tok = None
                    best_line = None
                    best_score = -1e9
                    y_pref = 0.60 * h
                    # 1) Prefer lines that are exactly a 12-digit token (whitespace allowed around)
                    for l in full_lines:
                        s = str(l.text).strip()
                        if re.fullmatch(r"\d{12}", s):
                            tok = s
                            c = float(getattr(l, "confidence", 0.0))
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            vdist = abs(cy - y_pref) / max(1.0, 0.30 * h)
                            lz = len(tok) - len(tok.lstrip('0'))
                            score = c - 0.2 * vdist - 0.05 * lz
                            if score > best_score:
                                best_score = score
                                best_tok = tok
                                best_line = l
                    # 2) If none, fall back to boundary 12-digit tokens inside lines without Latin letters/punct
                    if best_tok is None:
                        for l in full_lines:
                            s = str(l.text)
                            # reject if letters/punct in the line
                            if re.search(r"[A-Za-z]", s) or re.search(r"[\:\"A-Z]", s):
                                continue
                            for m in re.finditer(r"(?<!\\d)\\d{12}(?!\\d)", s):
                                tok = m.group(0)
                                c = float(getattr(l, "confidence", 0.0))
                                cy = float(getattr(l, "center", (0.0, 0.0))[1])
                                vdist = abs(cy - y_pref) / max(1.0, 0.30 * h)
                                lz = len(tok) - len(tok.lstrip('0'))
                                score = c - 0.2 * vdist - 0.05 * lz
                                if score > best_score:
                                    best_score = score
                                    best_tok = tok
                                    best_line = l
                    # 3) If none, try joins (4x4x4, 6x6)
                    if best_tok is None:
                        for l in full_lines:
                            s = str(l.text)
                            m = re.search(r"(?<!\\d)(\\d{4})\\D{1,3}(\\d{4})\\D{1,3}(\\d{4})(?!\\d)", s)
                            if m:
                                tok = m.group(1) + m.group(2) + m.group(3)
                                c = float(getattr(l, "confidence", 0.0))
                                cy = float(getattr(l, "center", (0.0, 0.0))[1])
                                vdist = abs(cy - y_pref) / max(1.0, 0.30 * h)
                                lz = len(tok) - len(tok.lstrip('0'))
                                score = c - 0.2 * vdist - 0.05 * lz - 0.10
                                if score > best_score:
                                    best_score = score
                                    best_tok = tok
                                    best_line = l
                            m2 = re.search(r"(?<!\\d)(\\d{6})\\D{1,3}(\\d{6})(?!\\d)", s)
                            if m2:
                                tok2 = m2.group(1) + m2.group(2)
                                c2 = float(getattr(l, "confidence", 0.0))
                                cy2 = float(getattr(l, "center", (0.0, 0.0))[1])
                                vdist2 = abs(cy2 - y_pref) / max(1.0, 0.30 * h)
                                lz2 = len(tok2) - len(tok2.lstrip('0'))
                                score2 = c2 - 0.2 * vdist2 - 0.05 * lz2 - 0.10
                                if score2 > best_score:
                                    best_score = score2
                                    best_tok = tok2
                                    best_line = l
                    if best_tok is not None:
                        text = best_tok
                        ocr_conf = max(float(ocr_conf), float(getattr(best_line, "confidence", 0.0)))
                        ocr_lang = "en"
                        # override bbox to the selected line for audit clarity
                        selected_src = "bm_final_full_image"
                        pts = getattr(best_line, "bbox", None)
                        if pts:
                            xs = [int(p[0]) for p in pts]
                            ys = [int(p[1]) for p in pts]
                            bx1 = max(0, min(xs) - int(0.02 * w_img))
                            by1 = max(0, min(ys) - int(0.02 * h))
                            bx2 = min(w_img - 1, max(xs) + int(0.02 * w_img))
                            by2 = min(h - 1, max(ys) + int(0.02 * h))
                            bbox = (bx1, by1, bx2, by2)
                except Exception:
                    pass
            if field == "cheque_number" and text:
                s = re.sub(r"\s+", "", str(text))
                # Prefer exact 12-digit tokens for CIB only; enforce 14 for NBE
                if bank.upper() == "CIB":
                    groups = re.findall(r"\d+", s)
                    # Filter to 12-digit groups first
                    twelves = [g for g in groups if len(g) == 12]
                    if twelves:
                        text = twelves[0]
                    else:
                        # Fall back to tokens within 10–13 digits, pick closest to 12 and avoid >13 (MICR)
                        rng = [g for g in groups if 10 <= len(g) <= 13]
                        if rng:
                            rng.sort(key=lambda g: (abs(len(g) - 12), -len(g)))
                            text = rng[0]
                elif bank.upper() == "NBE":
                    # Enforce 14-digit cheque number when available; also accept 7x7 join
                    m = re.search(r"(?<!\d)\d{14}(?!\d)", s)
                    if m:
                        text = m.group(0)
                    else:
                        j = re.search(r"(?<!\d)(\d{7})\D{1,3}(\d{7})(?!\d)", str(text))
                        if j:
                            text = j.group(1) + j.group(2)
                elif bank.upper() == "BANQUE_MISR":
                    # Extract exact boundary 8-digit token; if none, clear to avoid label spillover like 'Cheque'
                    m = re.search(r"(?<!\\d)\\d{8}(?!\\d)", str(text))
                    text = m.group(0) if m else ""
                elif bank.upper() == "AAIB":
                    # Prefer boundary 9 digits exactly; strip whitespace
                    m = re.search(r"(?<!\\d)\\d{9}(?!\\d)", s)
                    if m:
                        text = m.group(0)
                else:
                    m = NUM_RX.search(s)
                    if m:
                        text = m.group(0)
        parsed = parse_and_normalize(field, text)
        parse_ok = bool(parsed.get("parse_ok", False))
        loc_conf = float(rec.get('confidence', 0.0))
        field_conf = compute_field_confidence(
            ocr_conf=float(ocr_conf),
            locator_conf=loc_conf,
            parse_ok=parse_ok,
        )
        meets = passes_global_threshold(field_conf)
        fields[field] = {
            "field_conf": float(field_conf),
            "loc_conf": float(loc_conf),
            "ocr_conf": float(ocr_conf),
            "validation": {"ok": bool(meets)},
            "parse_ok": parse_ok,
            "parse_norm": parsed.get("norm"),
            "ocr_text": text or None,
            "ocr_lang": ocr_lang or None,
            "meets_threshold": bool(meets),
            "bbox": [bx1, by1, bx2, by2],
            **({"source": selected_src} if field == "cheque_number" else {}),
        }
    return fields
