from __future__ import annotations

import argparse
import json
import os
from glob import glob
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

from app.ocr import PaddleOCREngine, OCRLine


def _load_image(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    # Fallback if imdecode fails for any reason
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Failed to read image: {path}")
    return img


def _ocr_lines_to_json(lines: List[OCRLine]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for l in lines:
        # Convert polygon to bbox_rect for convenience
        xs = [p[0] for p in l.bbox]
        ys = [p[1] for p in l.bbox]
        x1, y1, x2, y2 = float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
        out.append(
            {
                "text": l.text,
                "raw_text": l.raw_text,
                "lang": l.lang,
                "confidence": float(l.confidence),
                "bbox": [[float(x), float(y)] for (x, y) in l.bbox],
                "bbox_rect": [x1, y1, x2, y2],
                "center_x": float(l.center[0]),
                "center_y": float(l.center[1]),
                "engine": l.engine,
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run PaddleOCREngine over images and write JSON outputs")
    ap.add_argument("root", help="Root folder containing images (e.g., sample_images/). Bank folders optional.")
    ap.add_argument("--out", default=os.path.join("backend", "reports", "ocr_lines"))
    ap.add_argument("--langs", nargs="+", default=["en", "ar"], help="Languages to use (default: en ar)")
    ap.add_argument("--min-conf", type=float, default=0.3, help="Min confidence to keep a line")
    args = ap.parse_args()

    engine = PaddleOCREngine()

    # Collect images: if subfolders exist, treat their name as bank label; else bank=UNKNOWN
    candidates: List[Tuple[str, str]] = []
    if os.path.isdir(args.root):
        # Include common image extensions
        subdirs = [d for d in glob(os.path.join(args.root, "*")) if os.path.isdir(d)]
        exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff")
        if subdirs:
            for sd in subdirs:
                bank = os.path.basename(sd)
                for ext in exts:
                    candidates.extend((bank, p) for p in glob(os.path.join(sd, ext)))
        else:
            for ext in exts:
                for p in glob(os.path.join(args.root, ext)):
                    candidates.append(("UNKNOWN", p))
    else:
        raise SystemExit(f"Root path is not a directory: {args.root}")

    if not candidates:
        print(f"No images found under {args.root}")
        return 1

    os.makedirs(args.out, exist_ok=True)

    for bank, path in candidates:
        try:
            img = _load_image(path)
            lines = engine.ocr_image(img, languages=args.langs, min_confidence=args.min_conf)
            result = {
                "file": path,
                "bank": bank,
                "lines": _ocr_lines_to_json(lines),
                "image_metadata": {
                    "width": int(img.shape[1]),
                    "height": int(img.shape[0]),
                    "channels": int(img.shape[2]) if img.ndim == 3 else 1,
                    "dtype": str(img.dtype),
                },
            }
            bank_dir = os.path.join(args.out, bank)
            os.makedirs(bank_dir, exist_ok=True)
            base = os.path.splitext(os.path.basename(path))[0]
            out_path = os.path.join(bank_dir, f"{base}_ocr.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"Wrote {out_path}")
        except Exception as e:
            print(f"Failed {path}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
