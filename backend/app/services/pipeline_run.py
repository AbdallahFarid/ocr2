from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

from app.ocr import PaddleOCREngine
from app.pipeline.postprocess import parse_and_normalize
from app.validations.confidence import compute_field_confidence, passes_global_threshold
from app.ocr.locator import locate_fields
from app.ocr.text_utils import fix_arabic_text

AMOUNT_RX = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
AMOUNT_DEC_RX = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")
DATE_RX = re.compile(r"\b\d{1,2}[\/-][A-Za-z0-9]{3}[\/-]\d{2,4}\b")
NUM_RX = re.compile(r"\b\d{6,}\b")
LABEL_NO_RX = re.compile(r"\b[nN][oO0]\b")


def _load_image(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Failed to read image: {path}")
    return img


def _ocr_lines_for_locator(lines: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for l in lines:
        out.append({
            "text": l.text,
            "confidence": float(l.confidence),
            "pos": [int(round(l.center[0])), int(round(l.center[1]))],
        })
    return out


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
            # Fallback to center with zero width
            cx = float(getattr(obj, "center", (0.0, 0.0))[0]) if hasattr(obj, "center") else 0.0
            return (cx, cx)

        def _rev_ar_token(s: str) -> str:
            try:
                return s[::-1]
            except Exception:
                return s

        texts: list[str] = []
        for l in ordered_lines:
            raw_t = str(getattr(l, "text", "")).strip()
            if not raw_t:
                continue
            # Reverse per-token text to convert possible visual-order output to logical Arabic
            t = _rev_ar_token(raw_t)
            texts.append(t)
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
        avg_conf = float(sum(float(getattr(l, "confidence", 0.0)) for l in ordered_lines) / max(1, len(ordered_lines)))
        return joined, avg_conf, "ar"
    text, conf, lang = _select_best_text(field, lines)
    if field == "date" and not DATE_RX.search(text or ""):
        bx1, by1, bx2, by2 = bbox
        exp = int(0.03 * w)
        nb = (max(0, bx1 - exp), by1, min(w - 1, bx2 + exp), by2)
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
    h, w_img = img.shape[:2]
    engine = PaddleOCREngine()
    # Precompute some global OCR lines
    full_lines_en = engine.ocr_image(img, languages=["en"], min_confidence=min_conf)
    no_lines = [l for l in full_lines_en if LABEL_NO_RX.search(str(l.text))]
    full_lines = engine.ocr_image(img, languages=langs, min_confidence=min_conf)
    loc_lines = _ocr_lines_for_locator(full_lines)
    loc = locate_fields(image_shape=(h, w_img), bank_id=bank, template_id=template_id, ocr_lines=loc_lines)

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
            if field == "cheque_number" and not NUM_RX.search(text or ""):
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
                        if abs(ny - cy) <= 0.05 * h and nx <= cx <= nx + 0.35 * w_img:
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
                    best = sorted(
                        candidates,
                        key=lambda d: (
                            0 if (d["has_no"] or d["has_no_near"]) else 1,
                            d["lead_zeros"],
                            abs(len(d["token"]) - 8),
                            abs(d["cy"] - cy_roi) + 0.5 * abs(d["cx"] - cx_roi),
                            0 if d["cy"] <= 0.4 * h else 1,
                            -d["confidence"],
                        ),
                    )[0]
                    text, ocr_conf, ocr_lang = best["token"], best["confidence"], best["lang"]
            if field == "cheque_number" and text:
                m = NUM_RX.search(text)
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
        }
    return fields
