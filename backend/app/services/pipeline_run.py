from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple, Optional

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

AMOUNT_RX = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
AMOUNT_DEC_RX = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")
# Accept dates like 30/Apr/2030, 30-Apr-2030, allow missing separators and extra punctuation,
# and tolerate trailing -1 or .1 from OCR noise. No leading word boundary required.
DATE_RX = re.compile(r"(?i)(?<!\d)\d{1,2}\s*[\/\-\.]?\s*[A-Za-z]{3}\s*[\/\-\.]?\s*\d{2,4}(?:[-\.]\d{1,2})?(?!\d)")
NUM_RX = re.compile(r"\b\d{6,}\b")
LABEL_NO_RX = re.compile(r"\b[nN][oO0]\b")


def _load_image(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Failed to read image: {path}")
    return img


def _maybe_downscale(img: np.ndarray, *, max_width: int = 1800) -> np.ndarray:
    """Downscale very large cheques to speed up OCR and avoid engine stalls.

    Preserves aspect ratio. Uses INTER_AREA for quality downscaling.
    """
    try:
        h, w = img.shape[:2]
    except Exception:
        return img
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


def _best_text_from_roi(engine: PaddleOCREngine, img: np.ndarray, bbox: Tuple[int, int, int, int], field: str, min_conf: float) -> Tuple[str, float, str]:
    langs = ["ar"] if field == "name" else ["en"]
    h, w = img.shape[:2]
    lines = engine.ocr_roi(img, roi=bbox, languages=langs, min_confidence=min_conf, padding=6, n_votes=3)
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
        lines2 = engine.ocr_roi(img, roi=nb, languages=langs, min_confidence=min_conf, padding=6, n_votes=3)
        if lines2:
            t2, c2, l2 = _select_best_text(field, lines2)
            if DATE_RX.search(t2 or "") and c2 >= conf:
                return t2, c2, l2
    if field == "amount_numeric" and (not AMOUNT_DEC_RX.search(text or "")):
        bx1, by1, bx2, by2 = bbox
        exp = int(0.06 * w)
        nb = (bx1, by1, min(w - 1, bx2 + exp), by2)
        lines2 = engine.ocr_roi(img, roi=nb, languages=langs, min_confidence=min_conf, padding=6, n_votes=3)
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
        langs = ["en", "ar"]
    img = _load_image(image_path)
    img = _maybe_downscale(img)
    h, w_img = img.shape[:2]
    engine = _get_engine()
    # Precompute some global OCR lines
    full_lines_en = engine.ocr_image(img, languages=["en"], min_confidence=min_conf)
    no_lines = [l for l in full_lines_en if LABEL_NO_RX.search(str(l.text))]
    full_lines = engine.ocr_image(img, languages=langs, min_confidence=min_conf)
    # Persist raw OCR lines for debugging/inspection
    try:
        _write_raw_ocr_lines(bank, image_path, full_lines)
    except Exception:
        pass
    loc_lines = _ocr_lines_for_locator(full_lines)
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
            text, ocr_conf, ocr_lang = _best_text_from_roi(engine, img, bbox, field, min_conf)
        selected_src: Optional[str] = None
        # AAIB: Re-scan ROI to extract exact 9–10 digit cheque number; fallback to top-left band near 'Cheque No.'
        if field == "cheque_number" and bank.upper() == "AAIB":
            try:
                # 1) ROI re-scan for boundary 9–10 digit tokens
                roi_lines = engine.ocr_roi(img, roi=bbox, languages=["en"], min_confidence=min_conf, padding=6, n_votes=3)
                cx_roi = 0.5 * (bbox[0] + bbox[2])
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
                    for m in re.finditer(r"(?<!\\d)\\d{9,10}(?!\\d)", s):
                        tok = m.group(0)
                        sc = aaib_score(tok, l)
                        if sc > best_score:
                            best_score = sc
                            best_tok = (tok, float(getattr(l, "confidence", 0.0)))
                if best_tok is not None:
                    text = best_tok[0]
                    ocr_conf = max(float(ocr_conf), float(best_tok[1]))
                    ocr_lang = "en"
                    selected_src = "aaib_roi_rescan"
                # 2) If still not a valid token, search full-image lines in top-left and around 'Cheque No.'
                if not re.fullmatch(r"\\d{9,10}", str(text or "")):
                    label_lines = [l for l in full_lines_en if re.search(r"(?i)\\bcheque\\s*no\\.?\\b", str(l.text))]
                    best = None
                    best_s = -1e9
                    for l in full_lines_en:
                        s = str(l.text)
                        mm = list(re.finditer(r"(?<!\\d)\\d{9,10}(?!\\d)", s))
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
                        score = c + top_bonus + left_bonus + near_label
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
                # 3) If still not valid, attempt a multi-line ROI join to detect contiguous 9–10 digits
                if not re.fullmatch(r"\d{9,10}", str(text or "")):
                    try:
                        roi_lines2 = engine.ocr_roi(img, roi=bbox, languages=["en"], min_confidence=min_conf, padding=10, n_votes=5)
                        joined = " ".join([str(getattr(l, "text", "")) for l in (roi_lines2 or [])])
                        m = re.search(r"(?<!\d)\d{9,10}(?!\d)", joined)
                        if m:
                            text = m.group(0)
                            selected_src = selected_src or "aaib_roi_join"
                    except Exception:
                        pass

            except Exception:
                pass

        # AAIB: Date fallback — ROI rescan and region- or label-guided search on full image
        if field == "date" and bank.upper() == "AAIB" and not DATE_RX.search(str(text or "")):
            try:
                # 1) ROI rescan with stronger voting and padding
                roi_lines = engine.ocr_roi(img, roi=bbox, languages=["en"], min_confidence=min_conf, padding=8, n_votes=5)
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
                    text = best[0]
                    ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                    ocr_lang = "en"
                    selected_src = selected_src or "aaib_date_roi"
                # 2) If still missing, search full image top-right band for any date (scan all OCR lines)
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
                        text = best[0]
                        ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                        ocr_lang = "en"
                        selected_src = selected_src or "aaib_date_region"
                # 3) If still missing, use 'Date' label proximity: pick a date to the right on the same row (scan all OCR lines)
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
                            text = best[0]
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = selected_src or "aaib_date_label"
                    except Exception:
                        pass
                # 4) Final global fallback: any date anywhere on full-image (choose highest conf; scan all OCR lines)
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
                            text = best[0]
                            ocr_conf = max(float(ocr_conf), float(getattr(best[1], "confidence", 0.0)))
                            ocr_lang = "en"
                            selected_src = selected_src or "aaib_date_global"
                    except Exception:
                        pass
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
        # BANQUE_MISR/CIB: Prefer preselected 12-digit token from anchor band on full-image OCR
        preselected_used = False
        preselected_line = None
        if field == "cheque_number" and bank.upper() in ("BANQUE_MISR", "CIB") and (en_cheq is not None or ar_cheq is not None):
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
                # Collect 12-digit tokens from full_lines_en between x-anchors
                best_tok = None
                best_score = -1e9
                cx_band = 0.5 * (x_l + x_r)
                for l in full_lines_en:
                    cx = float(getattr(l, "center", (0.0, 0.0))[0])
                    cy = float(getattr(l, "center", (0.0, 0.0))[1])
                    if not (x_l <= cx <= x_r):
                        continue
                    s = str(l.text)
                    # reject if letters/punct
                    if re.search(r"[A-Za-z]", s) or re.search(r"[\:\"A-Z]", s):
                        continue
                    for m in re.finditer(r"(?<!\d)\d{12}(?!\d)", s):
                        tok = m.group(0)
                        c = float(getattr(l, "confidence", 0.0))
                        dist = abs(cx - cx_band) / max(1.0, 0.5 * (x_r - x_l))
                        vdist = abs(cy - y_pref) / max(1.0, 0.25 * h)
                        lz = len(tok) - len(tok.lstrip('0'))
                        prefix_boost = 0.15 if tok.startswith("100") else 0.0
                        prefix_pen = -0.05 if tok.startswith("7") else 0.0
                        score = c - 0.3 * dist - 0.2 * vdist - 0.05 * lz + prefix_boost + prefix_pen
                        if score > best_score:
                            best_score = score
                            best_tok = (tok, c, l)
                if best_tok is not None:
                    text = best_tok[0]
                    ocr_conf = max(float(ocr_conf), float(best_tok[1]))
                    ocr_lang = "en"
                    preselected_used = True
                    preselected_line = best_tok[2]
                    selected_src = "bm_preselect_band"
            except Exception:
                pass
        # BANQUE_MISR/CIB: Re-scan ROI to extract exact 12-digit token with highest confidence
        if field == "cheque_number" and bank.upper() in ("BANQUE_MISR", "CIB") and not preselected_used:
            try:
                roi_lines = engine.ocr_roi(img, roi=bbox, languages=["en"], min_confidence=min_conf, padding=6, n_votes=3)
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
                    prefix_boost = 0.15 if tok.startswith("100") else 0.0
                    prefix_pen = -0.05 if tok.startswith("7") else 0.0
                    return c - 0.3 * dist - 0.2 * vdist - 0.05 * lz + prefix_boost + prefix_pen
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
                # 2) If none, consider 13-digit tokens, trimming to 12 as fallback
                if best_tok is None:
                    for l in roi_lines or []:
                        for m in re.finditer(r"(?<!\d)\d{13}(?!\d)", str(l.text)):
                            full = m.group(0)
                            tok = full[:12]
                            s = score_tok(tok, l) - 0.2  # small penalty for trimmed
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
            # For BANQUE_MISR/CIB require exact 12-digit; for others allow 6+ digits
            if field == "cheque_number" and (
                (bank.upper() not in ("BANQUE_MISR", "CIB") and not NUM_RX.search(text or "")) or
                (bank.upper() in ("BANQUE_MISR", "CIB") and not re.search(r"(?<!\\d)\\d{12}(?!\\d)", str(text or "")))
            ):
                candidates = []
                cy_roi = 0.5 * (by1 + by2)
                cx_roi = 0.5 * (bx1 + bx2)
                for l in full_lines_en:
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
                        len_bias = abs(len(d["token"]) - 10)  # cheque numbers here are ~10–12 digits
                        no_penalty = 1 if (d["has_no"] or d["has_no_near"]) else 0
                        center_penalty = x_center_dist / max(1.0, 0.5 * w_img)
                        return (
                            no_penalty,          # avoid 'No' lines
                            y_top_pref,          # prefer upper half
                            len_bias,            # prefer 10–12 digits
                            center_penalty,      # prefer center x
                            -float(d["confidence"]),
                        )
                    best = sorted(candidates, key=_score)[0]
                    text, ocr_conf, ocr_lang = best["token"], best["confidence"], best["lang"]
                    selected_src = selected_src or "fallback_candidates"
            # Final enforcement: For BANQUE_MISR/CIB, if a clean 12-digit exists in full-image OCR, take the best
            if field == "cheque_number" and bank.upper() in ("BANQUE_MISR", "CIB"):
                try:
                    best_tok = None
                    best_line = None
                    best_score = -1e9
                    y_pref = 0.60 * h
                    # 1) Prefer lines that are exactly a 12-digit token (whitespace allowed around)
                    for l in full_lines_en:
                        s = str(l.text).strip()
                        if re.fullmatch(r"\d{12}", s):
                            tok = s
                            c = float(getattr(l, "confidence", 0.0))
                            cy = float(getattr(l, "center", (0.0, 0.0))[1])
                            vdist = abs(cy - y_pref) / max(1.0, 0.30 * h)
                            lz = len(tok) - len(tok.lstrip('0'))
                            prefix_boost = 0.15 if tok.startswith("100") else 0.0
                            score = c - 0.2 * vdist - 0.05 * lz + prefix_boost
                            if score > best_score:
                                best_score = score
                                best_tok = tok
                                best_line = l
                    # 2) If none, fall back to boundary 12-digit tokens inside lines without Latin letters/punct
                    if best_tok is None:
                        for l in full_lines_en:
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
                                prefix_boost = 0.15 if tok.startswith("100") else 0.0
                                score = c - 0.2 * vdist - 0.05 * lz + prefix_boost
                                if score > best_score:
                                    best_score = score
                                    best_tok = tok
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
                # Prefer exact 12-digit tokens for BANQUE_MISR/CIB
                if bank.upper() in ("BANQUE_MISR", "CIB"):
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
                        else:
                            # Final fallback: longest digit token under 16 digits
                            under = [g for g in groups if len(g) < 16]
                            if under:
                                under.sort(key=lambda g: -len(g))
                                text = under[0]
                elif bank.upper() == "AAIB":
                    # Prefer boundary 9–10 digits; strip punctuation
                    m = re.search(r"(?<!\\d)\\d{9,10}(?!\\d)", s)
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
