from __future__ import annotations

import json
import os
from glob import glob
from typing import Dict, List

BASE = os.path.join("backend", "reports", "ocr_lines")

def summarize(base: str = BASE) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    if not os.path.isdir(base):
        return out
    for bank_dir in sorted([d for d in glob(os.path.join(base, "*")) if os.path.isdir(d)]):
        bank = os.path.basename(bank_dir)
        files = sorted(glob(os.path.join(bank_dir, "*_ocr.json")))
        if not files:
            continue
        img_count = 0
        total_lines = 0
        sum_avg_conf = 0.0
        by_lang_conf: Dict[str, float] = {}
        by_lang_cnt: Dict[str, int] = {}
        for fp in files:
            try:
                data = json.load(open(fp, encoding="utf-8"))
            except Exception:
                continue
            lines: List[dict] = data.get("lines", [])
            if not lines:
                continue
            img_count += 1
            total_lines += len(lines)
            avg_conf = sum(float(l.get("confidence", 0.0)) for l in lines) / len(lines)
            sum_avg_conf += avg_conf
            for l in lines:
                lang = l.get("lang") or "unk"
                by_lang_conf[lang] = by_lang_conf.get(lang, 0.0) + float(l.get("confidence", 0.0))
                by_lang_cnt[lang] = by_lang_cnt.get(lang, 0) + 1
        if img_count:
            out[bank] = {
                "images": img_count,
                "avg_lines_per_image": round(total_lines / img_count, 1),
                "avg_conf_per_image": round(sum_avg_conf / img_count, 3),
                "avg_conf_by_lang": {k: round(by_lang_conf[k]/by_lang_cnt[k], 3) for k in by_lang_conf},
            }
    return out

if __name__ == "__main__":
    import pprint
    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(summarize())
