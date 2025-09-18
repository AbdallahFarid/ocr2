from __future__ import annotations

import argparse
import csv
import json
import os
from glob import glob
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

from app.ocr import PaddleOCREngine
import re
from app.ocr.locator_utils import norm_rect_to_pixels


def _load_image(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Failed to read image: {path}")
    return img


def _load_template(bank: str, template_id: str) -> Dict[str, Any]:
    base_dir = os.path.join(os.path.dirname(__file__), "..", "app", "ocr", "templates", bank)
    # Normalize path
    base_dir = os.path.abspath(base_dir)
    with open(os.path.join(base_dir, f"{template_id}.json"), "r", encoding="utf-8") as f:
        return json.load(f)


AMOUNT_RX = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
DATE_RX = re.compile(r"\b\d{1,2}[\/-][A-Za-z0-9]{3}[\/-]\d{2,4}\b")
NUM_RX = re.compile(r"\b\d{6,}\b")


def _best_text_for_field(field: str, lines: List[Dict[str, Any]]) -> Tuple[str, float, str]:
    if not lines:
        return "", 0.0, ""
    # Prefer field-specific patterns first
    candidates = lines
    if field == "amount_numeric":
        cand = [l for l in lines if AMOUNT_RX.search(str(l.get("text", "")))]
        if cand:
            candidates = cand
    elif field == "date":
        cand = [l for l in lines if DATE_RX.search(str(l.get("text", "")))]
        if cand:
            candidates = cand
    elif field == "cheque_number":
        cand = [l for l in lines if NUM_RX.search(str(l.get("text", "")))]
        if cand:
            candidates = cand
    best = max(candidates, key=lambda l: float(l.get("confidence", 0.0)))
    return str(best.get("text", "")), float(best.get("confidence", 0.0)), str(best.get("lang", ""))


def _ocr_roi(engine: PaddleOCREngine, img: np.ndarray, roi: Tuple[int, int, int, int], langs: List[str], min_conf: float) -> List[Dict[str, Any]]:
    lines = engine.ocr_roi(img, roi=roi, languages=langs, min_confidence=min_conf, padding=6, n_votes=3)
    out: List[Dict[str, Any]] = []
    for l in lines:
        xs = [p[0] for p in l.bbox]
        ys = [p[1] for p in l.bbox]
        x1, y1, x2, y2 = float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
        out.append({
            "text": l.text,
            "confidence": float(l.confidence),
            "lang": l.lang,
            "bbox_rect": [x1, y1, x2, y2],
        })
    return out


def evaluate(root_images: str, bank: str, template_id: str, out_csv: str, langs: List[str], min_conf: float) -> None:
    tpl = _load_template(bank, template_id)
    fields = [f for f in tpl.get("fields", [])]

    engine = PaddleOCREngine()

    # Collect images under root_images/bank/*.jpg
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff")
    candidates: List[str] = []
    for ext in exts:
        candidates.extend(glob(os.path.join(root_images, bank, ext)))
    candidates.sort()
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "bank", "field", "text", "confidence", "lang", "roi_x1", "roi_y1", "roi_x2", "roi_y2"])
        for path in candidates:
            try:
                img = _load_image(path)
                h, w_img = img.shape[0], img.shape[1]
                for fld in fields:
                    name = fld.get("name")
                    roi_norm = fld.get("roi_norm")
                    if not name or not roi_norm:
                        continue
                    x1, y1, x2, y2 = norm_rect_to_pixels((h, w_img), tuple(roi_norm))
                    # Per-field language constraints
                    field_langs = ["ar"] if name == "name" else ["en"]
                    lines = _ocr_roi(engine, img, (x1, y1, x2, y2), field_langs, min_conf)
                    text, conf, lang = _best_text_for_field(name, lines)
                    w.writerow([
                        os.path.basename(path), bank, name, text, f"{conf:.3f}", lang, x1, y1, x2, y2
                    ])
            except Exception as e:
                w.writerow([os.path.basename(path), bank, "<error>", str(e), "", "", "", "", "", ""])


def main() -> int:
    ap = argparse.ArgumentParser(description="Field-level OCR evaluation using template ROIs")
    ap.add_argument("root_images", help="Root folder with images, e.g. sample_images/")
    ap.add_argument("bank", help="Bank ID, e.g. FABMISR")
    ap.add_argument("--template", default="auto", help="Template ID, e.g. default or auto")
    ap.add_argument("--out", default=os.path.join("backend", "reports", "field_ocr"))
    ap.add_argument("--langs", nargs="+", default=["en", "ar"])
    ap.add_argument("--min-conf", type=float, default=0.3)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    out_csv = os.path.join(args.out, f"{args.bank}_field_ocr.csv")
    evaluate(args.root_images, args.bank, args.template, out_csv, args.langs, args.min_conf)
    print(f"Wrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
