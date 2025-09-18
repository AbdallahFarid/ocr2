from __future__ import annotations

import argparse
import csv
import json
import os
from glob import glob
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from app.services.pipeline_run import run_pipeline_on_image


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
        # l is OCRLine dataclass
        out.append({
            "text": l.text,
            "confidence": float(l.confidence),
            "pos": [int(round(l.center[0])), int(round(l.center[1]))],
        })
    return out


def evaluate(root_images: str, bank: str, template_id: str, out_dir: str, langs: List[str], min_conf: float) -> None:
    os.makedirs(out_dir, exist_ok=True)

    # Collect images
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff")
    candidates: List[str] = []
    for ext in exts:
        candidates.extend(glob(os.path.join(root_images, bank, ext)))
    candidates.sort()

    csv_path = os.path.join(out_dir, f"{bank}_pipeline_eval.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "file", "bank", "field", "method", "loc_conf",
            "ocr_text", "ocr_conf", "ocr_lang",
            "parse_norm", "parse_ok",
            "field_conf", "meets_threshold",
            "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
        ])
        for path in candidates:
            try:
                # Run shared pipeline function used by API
                fields = run_pipeline_on_image(path, bank=bank, template_id=template_id, langs=langs, min_conf=min_conf)
                for field, rec in fields.items():
                    bbox = rec.get('bbox') or [0, 0, 0, 0]
                    w.writerow([
                        os.path.basename(path), bank, field, rec.get('method', ''), f"{float(rec.get('loc_conf',0.0)):.3f}",
                        rec.get('ocr_text') or '', f"{float(rec.get('ocr_conf',0.0)):.3f}", rec.get('ocr_lang') or '',
                        rec.get('parse_norm') or '', str(bool(rec.get('parse_ok', False))).lower(),
                        f"{float(rec.get('field_conf',0.0)):.3f}", str(bool(rec.get('meets_threshold', False))).lower(),
                        int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                    ])
            except Exception as e:
                w.writerow([os.path.basename(path), bank, "<error>", str(e), "", "", "", "", "", "", "", ""]) 
    print(f"Wrote {csv_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate full pipeline: OCR -> Locator -> ROI OCR")
    ap.add_argument("root_images", help="Root folder with images, e.g. sample_images/")
    ap.add_argument("bank", help="Bank ID, e.g. FABMISR")
    ap.add_argument("--template", default="auto")
    ap.add_argument("--out", default=os.path.join("backend", "reports", "pipeline"))
    ap.add_argument("--langs", nargs="+", default=["en", "ar"])
    ap.add_argument("--min-conf", type=float, default=0.3)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    evaluate(args.root_images, args.bank, args.template, args.out, args.langs, args.min_conf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
