from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Tuple

from app.ocr.locator import locate_fields


def _coerce_lines(lines: List[Dict[str, Any]], image_shape: Tuple[int, int]) -> List[Dict[str, Any]]:
    """Ensure each line has pixel 'pos' [x,y]. Accepts:
    - pos as [x,y] pixels
    - pos_norm as [x,y] normalized
    - bbox or polygon ignored (not needed for this locator)
    """
    h, w = image_shape
    out: List[Dict[str, Any]] = []
    for ln in lines:
        pos = ln.get("pos")
        if pos and len(pos) >= 2:
            out.append({"text": ln.get("text", ""), "confidence": ln.get("confidence", 0.0), "pos": [int(pos[0]), int(pos[1])]} )
            continue
        posn = ln.get("pos_norm") or ln.get("center_norm")
        if posn and len(posn) >= 2:
            px = int(round(float(posn[0]) * w))
            py = int(round(float(posn[1]) * h))
            out.append({"text": ln.get("text", ""), "confidence": ln.get("confidence", 0.0), "pos": [px, py]} )
            continue
        # Skip if no usable center
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Run field locator from OCR JSON")
    p.add_argument("json_path", help="Path to OCR JSON containing image size and lines")
    p.add_argument("--bank", default="FABMISR", help="Bank ID (e.g., FABMISR)")
    p.add_argument("--template", default="default", help="Template ID")

    args = p.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    h = int(data.get("image_height"))
    w = int(data.get("image_width"))
    if not h or not w:
        print("image_height and image_width required in JSON", file=sys.stderr)
        return 2

    lines_raw = data.get("lines") or []
    lines = _coerce_lines(lines_raw, (h, w))

    results = locate_fields(
        image_shape=(h, w),
        bank_id=args.bank,
        template_id=args.template,
        ocr_lines=lines,
    )

    print(json.dumps({"bank": args.bank, "template": args.template, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
