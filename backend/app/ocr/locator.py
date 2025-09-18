from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Dict, List, Tuple, Any, Optional

from app.ocr.locator_utils import norm_rect_to_pixels


class TemplateNotFoundError(FileNotFoundError):
    pass


def _template_path(bank_id: str, template_id: str = "default") -> str:
    base = os.path.join(os.path.dirname(__file__), "templates", bank_id, f"{template_id}.json")
    return base


def load_template(bank_id: str, template_id: str = "default") -> Dict[str, Any]:
    path = _template_path(bank_id, template_id)
    if not os.path.exists(path):
        raise TemplateNotFoundError(f"Template not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _locate_unknown(
    image_shape: Tuple[int, int],
    ocr_lines: Optional[List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Heuristic locator for unknown templates using only OCR lines.

    Returns minimal set of fields: bank_name, date, cheque_number, amount_numeric, name
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not ocr_lines:
        return results
    h, w = image_shape

    def _bbox_around(px: int, py: int, wf: float = 0.20, hf: float = 0.08) -> Tuple[int, int, int, int]:
        bw, bh = int(wf * w), int(hf * h)
        x1 = max(0, px - bw // 2)
        y1 = max(0, py - bh // 2)
        x2 = min(w, x1 + bw)
        y2 = min(h, y1 + bh)
        return (x1, y1, x2, y2)

    def _best_match(pattern: str) -> Optional[Dict[str, Any]]:
        rx = re.compile(pattern, flags=re.IGNORECASE)
        best = None
        best_conf = -1.0
        for ln in ocr_lines:
            txt = str(ln.get("text", ""))
            if rx.search(txt):
                c = float(ln.get("confidence", 0.5))
                if c > best_conf:
                    best = ln
                    best_conf = c
        return best

    # bank_name: unknown
    results["bank_name"] = {
        "bbox": [0, 0, int(0.2 * w), int(0.1 * h)],
        "confidence": 0.5,
        "method": "unknown_bank",
        "ocr_engine": "latin",
        "text": "UNKNOWN",
    }

    # date
    date_ln = _best_match(r"\b\d{1,2}[\/\-][A-Za-z]{3}[\/\-]\d{2,4}\b")
    if date_ln:
        px, py = int(date_ln["pos"][0]), int(date_ln["pos"][1])
        results["date"] = {
            "bbox": list(_bbox_around(px, py)),
            "confidence": float(date_ln.get("confidence", 0.85)),
            "method": "unknown_regex",
            "ocr_engine": "latin",
            "text": str(date_ln.get("text", "")),
        }

    # amount
    amt_ln = _best_match(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
    if amt_ln:
        px, py = int(amt_ln["pos"][0]), int(amt_ln["pos"][1])
        results["amount_numeric"] = {
            "bbox": list(_bbox_around(px, py, wf=0.22, hf=0.10)),
            "confidence": float(amt_ln.get("confidence", 0.90)),
            "method": "unknown_regex",
            "ocr_engine": "latin",
            "text": str(amt_ln.get("text", "")),
        }

    # cheque number
    num_ln = _best_match(r"\b\d{6,}\b")
    if num_ln:
        px, py = int(num_ln["pos"][0]), int(num_ln["pos"][1])
        results["cheque_number"] = {
            "bbox": list(_bbox_around(px, py, wf=0.26, hf=0.10)),
            "confidence": float(num_ln.get("confidence", 0.85)),
            "method": "unknown_regex",
            "ocr_engine": "latin",
            "text": str(num_ln.get("text", "")),
        }

    # name: prefer Arabic, few digits, not a label, upper half band
    best_name = None
    best_score = -1.0
    for ln in ocr_lines:
        txt = str(ln.get("text", ""))
        t = txt
        conf = float(ln.get("confidence", 0.5))
        px, py = int(ln.get("pos", [0, 0])[0]), int(ln.get("pos", [0, 0])[1])
        # Skip obvious labels
        if re.search(r"(?i)\b(pay\s*to|against\s+this\s+cheque|date|egp)\b", t):
            continue
        if re.search(r"شيك|ادفع|بموجب|الشيك|هذا", t):
            continue
        ar = 1.0 if re.search(r"[\u0600-\u06FF]", t) else 0.0
        if ar == 0.0:
            continue
        digits = sum(ch.isdigit() for ch in t)
        length = max(1, len(t))
        if digits / float(length) > 0.2:
            continue
        # Prefer upper half and center region
        dy = abs(py - 0.35 * h) / float(h)
        dx = abs(px - 0.55 * w) / float(w)
        score = conf + 0.2 * ar - 0.3 * dy - 0.2 * dx + 0.1 * min(1.0, length / 20.0)
        if score > best_score:
            best_score = score
            best_name = ln
    if best_name is not None:
        px, py = int(best_name["pos"][0]), int(best_name["pos"][1])
        bbox = _bbox_around(px, py, wf=0.45, hf=0.10)
        results["name"] = {
            "bbox": list(bbox),
            "confidence": float(best_name.get("confidence", 0.85)),
            "method": "unknown_payee",
            "ocr_engine": "arabic",
            "text": str(best_name.get("text", "")),
        }
    return results


def locate_fields(
    image_shape: Tuple[int, int],
    bank_id: str,
    template_id: str = "default",
    ocr_lines: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Locate fields for a known template using static normalized ROIs.

    Returns a mapping: field_name -> { bbox: [x1,y1,x2,y2], confidence: float, method: str }
    """
    # Load template, or fallback to unknown-template heuristics
    try:
        template = load_template(bank_id, template_id)
    except TemplateNotFoundError:
        return _locate_unknown(image_shape, ocr_lines)
    results: Dict[str, Dict[str, Any]] = {}

    def lines_in_region(region_norm: List[float]) -> List[Dict[str, Any]]:
        x1, y1, x2, y2 = norm_rect_to_pixels(image_shape, tuple(region_norm))
        hits: List[Dict[str, Any]] = []
        if not ocr_lines:
            return hits
        for ln in ocr_lines:
            pos = ln.get("pos") or ln.get("center") or ln.get("point")
            if not pos or len(pos) < 2:
                continue
            px, py = int(pos[0]), int(pos[1])
            if x1 <= px <= x2 and y1 <= py <= y2:
                hits.append(ln)
        return hits

    def _norm_text(s: str) -> str:
        try:
            return unicodedata.normalize("NFKC", s)
        except Exception:
            return s

    def best_regex_match(lines: List[Dict[str, Any]], pattern: str) -> Optional[Dict[str, Any]]:
        if not lines:
            return None
        rx = re.compile(pattern, flags=re.IGNORECASE)
        best = None
        best_score = -1.0
        for ln in lines:
            txt = str(ln.get("text", ""))
            if rx.search(_norm_text(txt)):
                score = float(ln.get("confidence", 0.5))
                if score > best_score:
                    best = ln
                    best_score = score
        return best

    # Build anchors from template
    anchors_cfg = template.get("anchors", [])
    anchors_found: Dict[str, Dict[str, Any]] = {}
    for a in anchors_cfg:
        pattern = a.get("pattern")
        region_norm = a.get("region_norm")
        if not pattern or not region_norm:
            continue
        cand = lines_in_region(region_norm)
        hit = best_regex_match(cand, pattern)
        if hit is not None:
            anchors_found[a.get("name", pattern)] = hit

    for field in template.get("fields", []):
        name = field["name"]
        engine = field.get("ocr_engine", "latin")
        method = "template_roi"
        confidence = 0.9
        bbox: Tuple[int, int, int, int]

        # 1) Anchor-based payee name using 'pay_to' anchors: select best-scoring line to the RIGHT of the anchor
        if name == "name" and ocr_lines:
            pay_en = anchors_found.get("pay_to_label")
            pay_ar = anchors_found.get("pay_to_label_ar")
            if pay_en is not None or pay_ar is not None:
                h, w = image_shape
                x_mid: Optional[float] = None
                if pay_en is not None and pay_ar is not None:
                    ax1, ay1 = int(pay_en["pos"][0]), int(pay_en["pos"][1])
                    ax2, ay2 = int(pay_ar["pos"][0]), int(pay_ar["pos"][1])
                    x_left, x_right = (ax1, ax2) if ax1 < ax2 else (ax2, ax1)
                    cy = int((ay1 + ay2) / 2)
                    y_top = max(0, cy - int(0.10 * h))
                    # Add a small margin to avoid picking anchors on the edges
                    x_margin = int(0.02 * w)
                    x_l = max(0, x_left + x_margin)
                    x_r = min(w, x_right - x_margin)
                    region_norm = [x_l / w, y_top / h, max(0.0, (x_r - x_l) / w), 0.22]
                    x_mid = (x_l + x_r) / 2.0
                else:
                    # Only one anchor
                    a = pay_en or pay_ar
                    ax, ay = int(a["pos"][0]), int(a["pos"][1])
                    y_top = max(0, ay - int(0.08 * h))
                    if a is pay_en:
                        # English anchor: payee to the right
                        region_norm = [ax / w, y_top / h, max(0.0, 1.0 - ax / w), 0.20]
                    else:
                        # Arabic anchor: payee to the left
                        region_norm = [0.0, y_top / h, min(0.98, ax / w), 0.20]

                cand_lines = lines_in_region(region_norm)
                best = None
                best_score = -1.0
                for ln in cand_lines:
                    px, py = int(ln.get("pos", [0, 0])[0]), int(ln.get("pos", [0, 0])[1])
                    # If only English anchor present: require to the right; if only Arabic anchor present: require to the left
                    if pay_en is not None and pay_ar is None:
                        if px <= int(pay_en["pos"][0]) + int(0.02 * w):
                            continue
                    if pay_ar is not None and pay_en is None:
                        if px >= int(pay_ar["pos"][0]) - int(0.02 * w):
                            continue
                    txt = str(ln.get("text", ""))
                    t = _norm_text(txt)
                    conf = float(ln.get("confidence", 0.5))
                    if conf < 0.6:
                        continue
                    # Exclude amount-related or currency labels
                    if re.search(r"(?i)\b(the\s+sum\s+of)\b", t) or re.search(r"(?i)\begp\b", t):
                        continue
                    # Exclude pay-to label lines themselves (English/Arabic)
                    if re.search(r"(?i)pay\s+.*this\s+cheque\s+.*order\s+of", t):
                        continue
                    # Exclude common labels in QNB and others
                    if re.search(r"(?i)\bagainst\s+this\s+cheque\b", t):
                        continue
                    if re.search(r"(?i)\bpay\s*to\b", t) or re.search(r"(?i)\bpayto\b", t):
                        continue
                    # Arabic pay-this-cheque lines often contain these keywords; exclude if present
                    # Use flexible spacing and optional diacritics/hamza forms
                    t_ns = re.sub(r"\s+", "", t)
                    if (
                        re.search(r"شيك", t) or  # contains 'cheque'
                        re.search(r"ادفع", t) or  # 'pay'
                        re.search(r"بموجب", t) or  # 'by virtue of'
                        re.search(r"هذا", t) or  # 'this'
                        re.search(r"الشيك", t) or  # 'the cheque'
                        re.search(r"ل\s*أ\s*مر|لا\s*مر|لٱمر|لآمر", t) or  # 'to the order of' variants
                        re.search(r"هذا.*الشيك", t_ns)  # compact form
                    ):
                        continue
                    # If we have 'sum_label' anchor, prefer lines above it by excluding those clearly below
                    sum_anchor = anchors_found.get("sum_label")
                    if sum_anchor is not None:
                        sy = int(sum_anchor["pos"][1])
                        if py > sy - int(0.02 * h):
                            continue
                    # Penalize lines with many digits (likely amounts or numbers)
                    digits = sum(ch.isdigit() for ch in t)
                    length = max(1, len(t))
                    digit_ratio = digits / float(length)
                    if digit_ratio > 0.3:
                        continue
                    # Filter out very short tokens which are often stray words (e.g., short Arabic like 'عفلا')
                    ar_chars = len(re.findall(r"[\u0600-\u06FF]", t))
                    if ar_chars > 0 and ar_chars < 6:
                        continue
                    if ar_chars == 0 and length < 6:
                        continue
                    # Score by vertical proximity and confidence, slight boost for Arabic text
                    dy = abs(py - ay) / float(h)
                    is_ar = 1.0 if re.search(r"[\u0600-\u06FF]", t) else 0.0
                    # Keyword boost for company/payee cues
                    kw_boost = 0.0
                    if re.search(r"شركة|شركه", t):
                        kw_boost += 0.2
                    if re.search(r"(?i)\bcompany\b|\bco\.?\b", t):
                        kw_boost += 0.1
                    short_penalty = -0.2 if length < 10 else 0.0
                    score = conf * 1.0 - dy * 0.6 + is_ar * 0.1 + kw_boost + short_penalty
                    # If both anchors exist, penalize distance from the mid x to favor central payee text
                    if x_mid is not None:
                        dx = abs(px - x_mid) / float(w)
                        score -= 0.4 * dx
                    if score > best_score:
                        best = ln
                        best_score = score
                if best is not None:
                    px, py = int(best["pos"][0]), int(best["pos"][1])
                    bw, bh = int(0.45 * w), int(0.10 * h)
                    x1 = max(0, px - bw // 2)
                    y1 = max(0, py - bh // 2)
                    x2 = min(w, x1 + bw)
                    y2 = min(h, y1 + bh)
                    bbox = (x1, y1, x2, y2)
                    method = "anchor_payee_scored"
                    confidence = float(best.get("confidence", 0.85))
                    results[name] = {
                        "bbox": list(bbox),
                        "confidence": confidence,
                        "method": method,
                        "ocr_engine": engine,
                        "text": str(best.get("text", "")),
                        "anchor": "pay_to",
                    }
                    continue

        # 2) Pattern + region search
        if "pattern" in field and "region_norm" in field and ocr_lines:
            cand_lines = lines_in_region(field["region_norm"])  # type: ignore[arg-type]
            match = best_regex_match(cand_lines, field["pattern"])  # type: ignore[arg-type]
            # For date field, enforce a strict date pattern; if not matched, skip to alternative strategies
            if match is not None and name == "date":
                txtn = _norm_text(str(match.get("text", "")))
                if not re.search(r"\b\d{1,2}[\/\-][A-Za-z]{3}[\/\-]\d{2,4}\b", txtn):
                    match = None
            if match is not None:
                px, py = int(match["pos"][0]), int(match["pos"][1])
                h, w = image_shape
                # Create a tight bbox around the matched center (heuristic size)
                bw, bh = int(0.20 * w), int(0.08 * h)
                x1 = max(0, px - bw // 2)
                y1 = max(0, py - bh // 2)
                x2 = min(w, x1 + bw)
                y2 = min(h, y1 + bh)
                bbox = (x1, y1, x2, y2)
                method = "region_regex"
                confidence = float(match.get("confidence", 0.85))
                results[name] = {
                    "bbox": list(bbox),
                    "confidence": confidence,
                    "method": method,
                    "ocr_engine": engine,
                    "text": str(match.get("text", "")),
                }
                continue

        # 3) Anchor-refined date and amount if labels found but pattern region fails
        if name == "date" and "roi_norm" in field and "date_label" in anchors_found and ocr_lines:
            lab = anchors_found["date_label"]
            px, py = int(lab["pos"][0]), int(lab["pos"][1])
            h, w = image_shape
            region_norm = [min(1.0, px / w), max(0.0, (py - 0.10 * h) / h), min(0.35, 1.0 - px / w), 0.22]
            cand_lines = lines_in_region(region_norm)
            # Look for date-like text
            match = best_regex_match(cand_lines, r"\b\d{1,2}[\/\-][A-Za-z]{3}[\/\-]\d{4}\b")
            if match is not None:
                px2, py2 = int(match["pos"][0]), int(match["pos"][1])
                bw, bh = int(0.20 * w), int(0.08 * h)
                x1 = max(0, px2 - bw // 2)
                y1 = max(0, py2 - bh // 2)
                x2 = min(w, x1 + bw)
                y2 = min(h, y1 + bh)
                bbox = (x1, y1, x2, y2)
                results[name] = {
                    "bbox": list(bbox),
                    "confidence": float(match.get("confidence", 0.85)),
                    "method": "anchor_date_right",
                    "ocr_engine": engine,
                    "text": str(match.get("text", "")),
                    "anchor": "date_label",
                }
                continue

        if name == "amount_numeric" and "roi_norm" in field and "egp_label" in anchors_found and ocr_lines:
            lab = anchors_found["egp_label"]
            px, py = int(lab["pos"][0]), int(lab["pos"][1])
            h, w = image_shape
            region_norm = [min(1.0, px / w), max(0.0, (py - 0.10 * h) / h), min(0.40, 1.0 - px / w), 0.25]
            cand_lines = lines_in_region(region_norm)
            match = best_regex_match(cand_lines, r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
            if match is not None:
                px2, py2 = int(match["pos"][0]), int(match["pos"][1])
                bw, bh = int(0.22 * w), int(0.10 * h)
                x1 = max(0, px2 - bw // 2)
                y1 = max(0, py2 - bh // 2)
                x2 = min(w, x1 + bw)
                y2 = min(h, y1 + bh)
                bbox = (x1, y1, x2, y2)
                results[name] = {
                    "bbox": list(bbox),
                    "confidence": float(match.get("confidence", 0.90)),
                    "method": "anchor_egp_right",
                    "ocr_engine": engine,
                    "text": str(match.get("text", "")),
                    "anchor": "egp_label",
                }
                continue

        # 4) Fallback to static ROI if present
        if "roi_norm" in field:
            roi_norm = tuple(field["roi_norm"])  # [x,y,w,h]
            bbox = norm_rect_to_pixels(image_shape, roi_norm)
            results[name] = {
                "bbox": list(bbox),
                "confidence": confidence,
                "method": method,
                "ocr_engine": engine,
            }
            continue

    return results


__all__ = ["load_template", "locate_fields", "TemplateNotFoundError"]
