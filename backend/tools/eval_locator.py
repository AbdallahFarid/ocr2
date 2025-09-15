from __future__ import annotations

import argparse
import csv
import json
import os
from glob import glob
from typing import Any, Dict, List, Tuple, Optional

from app.ocr.locator import locate_fields
from app.ocr.locator_utils import norm_rect_to_pixels


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _collect_json_files(root: str) -> List[Tuple[str, str]]:
    """Return list of (bank_id, json_path). bank_id is parent dir name under root.
    Accepts any *.json under immediate subfolders.
    """
    items: List[Tuple[str, str]] = []
    # Search only one-level deep: root/<BANK>/*.json
    for bank_dir in sorted([d for d in glob(os.path.join(root, "*")) if os.path.isdir(d)]):
        bank = os.path.basename(bank_dir)
        for jp in sorted(glob(os.path.join(bank_dir, "*.json"))):
            items.append((bank, jp))
    return items


def _normalize_lines_from_old_schema(data: Dict[str, Any]) -> Tuple[Tuple[int, int], List[Dict[str, Any]]]:
    # Image dimensions
    meta = data.get("image_metadata", {})
    h = int(meta.get("height") or 0)
    w = int(meta.get("width") or 0)
    if not h or not w:
        # try top-level keys
        h = int(data.get("image_height") or 0)
        w = int(data.get("image_width") or 0)
    if not h or not w:
        raise ValueError("Image dimensions missing in OCR JSON")

    # Prefer modern 'lines', else fall back to 'raw_ocr_results'
    lines: List[Dict[str, Any]] = []
    if isinstance(data.get("lines"), list):
        for ln in data["lines"]:
            pos = ln.get("pos") or ln.get("center")
            if not pos and ln.get("pos_norm"):
                # convert from normalized
                pos = [int(round(float(ln["pos_norm"][0]) * w)), int(round(float(ln["pos_norm"][1]) * h))]
            if not pos:
                # try bbox_rect
                rect = ln.get("bbox_rect")
                if rect and len(rect) >= 4:
                    cx = int(round((float(rect[0]) + float(rect[2])) / 2))
                    cy = int(round((float(rect[1]) + float(rect[3])) / 2))
                    pos = [cx, cy]
            if pos:
                lines.append({
                    "text": ln.get("text", ""),
                    "confidence": float(ln.get("confidence", 0.0)),
                    "pos": [int(pos[0]), int(pos[1])],
                })
    elif isinstance(data.get("raw_ocr_results"), list):
        for ln in data["raw_ocr_results"]:
            # Expect center_x/center_y or bbox_rect
            pos = None
            cx = ln.get("center_x")
            cy = ln.get("center_y")
            if cx is not None and cy is not None:
                pos = [int(round(float(cx))), int(round(float(cy)))]
            else:
                rect = ln.get("bbox_rect")
                if rect and len(rect) >= 4:
                    pos = [int(round((float(rect[0]) + float(rect[2])) / 2)), int(round((float(rect[1]) + float(rect[3])) / 2))]
            if pos:
                lines.append({
                    "text": ln.get("text", ""),
                    "confidence": float(ln.get("confidence", 0.0)),
                    "pos": [int(pos[0]), int(pos[1])],
                })

    return (h, w), lines


def _best_line_in_bbox(lines: List[Dict[str, Any]], bbox: Tuple[int, int, int, int]) -> Optional[Dict[str, Any]]:
    x1, y1, x2, y2 = bbox
    best = None
    best_score = -1.0
    for ln in lines:
        px, py = int(ln["pos"][0]), int(ln["pos"][1])
        if x1 <= px <= x2 and y1 <= py <= y2:
            score = float(ln.get("confidence", 0.0))
            if score > best_score:
                best = ln
                best_score = score
    return best


def _ensure_out_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch-evaluate locator over OCR JSONs")
    ap.add_argument("root", help="Root folder containing bank subfolders, e.g. ocr_json/")
    ap.add_argument("--out", default=os.path.join("backend", "reports"), help="Output directory for CSV and per-file results")
    ap.add_argument("--template", default="default", help="Template ID to use")
    args = ap.parse_args()

    files = _collect_json_files(args.root)
    if not files:
        print(f"No OCR JSON files found under {args.root}")
        return 1

    _ensure_out_dir(args.out)
    csv_path = os.path.join(args.out, "locator_eval.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.writer(csvf)
        writer.writerow([
            "file",
            "bank",
            "field",
            "method",
            "confidence",
            "bbox_x1",
            "bbox_y1",
            "bbox_x2",
            "bbox_y2",
            "pattern_text",
            "roi_text",
            "match_flag",
        ])

        for bank, jp in files:
            try:
                data = _load_json(jp)
                image_shape, lines = _normalize_lines_from_old_schema(data)
                # Run locator (patterns+anchors+roi fallback)
                results = locate_fields(image_shape=image_shape, bank_id=bank, template_id=args.template, ocr_lines=lines)

                # Per-file JSON result
                out_json_path = os.path.join(args.out, f"{bank}_{os.path.splitext(os.path.basename(jp))[0]}_loc.json")
                with open(out_json_path, "w", encoding="utf-8") as f:
                    json.dump({"file": jp, "bank": bank, "results": results}, f, ensure_ascii=False, indent=2)

                # Also compute ROI-only text to compare
                # Load template fields if available to get roi_norm
                # Since locate_fields does not return roi_norm, we recompute from template JSON on demand
                # Quick load template JSON directly
                tpath = os.path.join(os.path.dirname(__file__), "templates", bank, f"{args.template}.json")
                roi_map: Dict[str, Tuple[int, int, int, int]] = {}
                if os.path.exists(tpath):
                    with open(tpath, "r", encoding="utf-8") as tf:
                        tdata = json.load(tf)
                        for fld in tdata.get("fields", []):
                            if "roi_norm" in fld:
                                roi_map[fld["name"]] = norm_rect_to_pixels(image_shape, tuple(fld["roi_norm"]))

                for field_name, rec in results.items():
                    bbox = rec.get("bbox", [0, 0, 0, 0])
                    method = rec.get("method", "")
                    conf = rec.get("confidence", 0.0)
                    pat_text = rec.get("text", "")

                    # ROI text (highest conf line within ROI if present)
                    roi_text = ""
                    if field_name in roi_map:
                        best_ln = _best_line_in_bbox(lines, roi_map[field_name])
                        if best_ln is not None:
                            roi_text = str(best_ln.get("text", ""))

                    # Simple normalization for match check
                    def _norm(s: str) -> str:
                        return "".join(ch for ch in s if ch.isalnum())[:128].lower()

                    match_flag = (bool(_norm(pat_text)) and _norm(pat_text) == _norm(roi_text))

                    writer.writerow([
                        os.path.basename(jp),
                        bank,
                        field_name,
                        method,
                        f"{conf:.3f}",
                        bbox[0],
                        bbox[1],
                        bbox[2],
                        bbox[3],
                        pat_text,
                        roi_text,
                        int(match_flag),
                    ])

            except Exception as e:
                # Write an error row for visibility
                writer.writerow([
                    os.path.basename(jp), bank, "<error>", "", "", "", "", "", "", f"{e}", "", 0
                ])

    print(f"Wrote report: {csv_path}\nPer-file results in: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
