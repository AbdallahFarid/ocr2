from __future__ import annotations

import argparse
import glob
import json
import os
from statistics import median
from typing import Any, Dict, List, Tuple


def _read_results(report_dir: str, bank: str) -> List[Dict[str, Any]]:
    paths = sorted(glob.glob(os.path.join(report_dir, f"{bank}_*_loc.json")))
    out = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            pass
    return out


def _to_norm_bbox(bbox: List[int], image_shape: Tuple[int, int]) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    h, w = image_shape
    x = max(0.0, min(1.0, x1 / w))
    y = max(0.0, min(1.0, y1 / h))
    rw = max(1e-6, min(1.0, (x2 - x1) / w))
    rh = max(1e-6, min(1.0, (y2 - y1) / h))
    return (x, y, rw, rh)


def _collect_norm_bboxes(items: List[Dict[str, Any]], field: str) -> List[Tuple[float, float, float, float]]:
    coll: List[Tuple[float, float, float, float]] = []
    for it in items:
        try:
            # Derive image shape from per-file path via ocr_json folder (we don't have height per item result)
            # Fallback to 677x1677 for FABMISR samples commonly used
            image_shape = (677, 1677)
            rec = it["results"].get(field)
            if not rec:
                continue
            bbox = rec.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            coll.append(_to_norm_bbox(bbox, image_shape))
        except Exception:
            continue
    return coll


def _robust_center_spread(vals: List[float]) -> Tuple[float, float]:
    if not vals:
        return (0.0, 0.0)
    med = median(vals)
    # simple MAD-like scale using middle 50% window approximated by 0.1
    spread = max(0.02, 1.4826 * median([abs(v - med) for v in vals]) if len(vals) > 2 else 0.05)
    return med, spread


def refine(bank: str, report_dir: str, out_template: str, base_template: str | None = None) -> None:
    items = _read_results(report_dir, bank)
    if not items:
        raise SystemExit(f"No per-file locator results for {bank} under {report_dir}")

    base = {"bank_id": bank, "template_id": "auto", "version": "0.1.0", "fields": [], "anchors": []}
    if base_template and os.path.exists(base_template):
        with open(base_template, "r", encoding="utf-8") as f:
            base = json.load(f)
            base["template_id"] = "auto"

    fields = ["bank_name", "date", "cheque_number", "amount_numeric", "name"]
    refined_fields: List[Dict[str, Any]] = []

    for fld in fields:
        norm_boxes = _collect_norm_bboxes(items, fld)
        if not norm_boxes:
            continue
        xs = [b[0] for b in norm_boxes]
        ys = [b[1] for b in norm_boxes]
        ws = [b[2] for b in norm_boxes]
        hs = [b[3] for b in norm_boxes]
        mx, sx = _robust_center_spread(xs)
        my, sy = _robust_center_spread(ys)
        mw, sw = _robust_center_spread(ws)
        mh, sh = _robust_center_spread(hs)
        # Build conservative roi around medians with padding
        pad = 1.0
        roi = [
            max(0.0, mx - pad * sx),
            max(0.0, my - pad * sy),
            min(1.0, mw + pad * sw),
            min(1.0, mh + pad * sh),
        ]
        # Keep region_norm same as roi for now; can be widened slightly
        region = [
            max(0.0, roi[0] - 0.02),
            max(0.0, roi[1] - 0.02),
            min(1.0, roi[2] + 0.04),
            min(1.0, roi[3] + 0.04),
        ]
        # Inherit engine and pattern if present in base template
        base_fields = {f.get("name"): f for f in base.get("fields", [])}
        bf = base_fields.get(fld, {})
        refined_fields.append({
            "name": fld,
            "roi_norm": [round(x, 3) for x in roi],
            "region_norm": [round(x, 3) for x in region],
            "ocr_engine": bf.get("ocr_engine", "latin" if fld != "name" else "arabic"),
            **({"pattern": bf["pattern"]} if "pattern" in bf else {}),
            "confidence_weight": 1.0,
        })

    base["fields"] = refined_fields

    out_dir = os.path.dirname(out_template)
    os.makedirs(out_dir, exist_ok=True)
    with open(out_template, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)
    print(f"Wrote refined template: {out_template}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Refine template roi/regions from per-file locator results")
    ap.add_argument("bank", help="Bank ID e.g. FABMISR")
    ap.add_argument("--reports", default=os.path.join("backend", "reports"))
    ap.add_argument("--base", default=None, help="Optional base template to inherit patterns/anchors from")
    ap.add_argument("--out", default=None, help="Output template path; defaults to templates/<bank>/auto.json")
    a = ap.parse_args()
    if not a.out:
        a.out = os.path.join(os.path.dirname(__file__), "templates", a.bank, "auto.json")
    refine(a.bank, a.reports, a.out, a.base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
