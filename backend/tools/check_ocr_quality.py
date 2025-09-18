from __future__ import annotations

import json
import os
import re
from glob import glob
from typing import Dict, List, Tuple

BASE = os.path.join("backend", "reports", "ocr_lines")

BANK_PATTERNS = {
    "FABMISR": re.compile(r"\bFABMISR\b", re.I),
    "QNB": re.compile(r"\bQNB\b", re.I),
}
DATE_PAT = re.compile(r"\b\d{1,2}[\/-][A-Za-z0-9]{3}[\/-]\d{2,4}\b")
EGP_PAT = re.compile(r"\bEGP\b", re.I)
COMPANY_AR_PAT = re.compile(r"شركة")


def _scan_file(fp: str, bank: str) -> Dict[str, bool]:
    try:
        data = json.load(open(fp, encoding="utf-8"))
    except Exception:
        return {"ok": False}
    lines: List[dict] = data.get("lines", [])
    texts = [str(l.get("text", "")) for l in lines]
    joined = "\n".join(texts)
    has_bank = False
    if bank in BANK_PATTERNS:
        has_bank = bool(BANK_PATTERNS[bank].search(joined))
    has_date = bool(DATE_PAT.search(joined))
    has_egp = bool(EGP_PAT.search(joined))
    has_company_ar = bool(COMPANY_AR_PAT.search(joined))
    return {
        "ok": True,
        "has_bank": has_bank,
        "has_date": has_date,
        "has_egp": has_egp,
        "has_company_ar": has_company_ar,
        "lines": len(lines),
    }


def summarize_quality(base: str = BASE) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for bank_dir in sorted([d for d in glob(os.path.join(base, "*")) if os.path.isdir(d)]):
        bank = os.path.basename(bank_dir)
        files = sorted(glob(os.path.join(bank_dir, "*_ocr.json")))
        if not files:
            continue
        stats = {"count": 0, "bank": 0, "date": 0, "egp": 0, "company_ar": 0, "avg_lines": 0.0}
        for fp in files:
            m = _scan_file(fp, bank)
            if not m.get("ok"):
                continue
            stats["count"] += 1
            stats["avg_lines"] += m.get("lines", 0)
            stats["bank"] += 1 if m.get("has_bank") else 0
            stats["date"] += 1 if m.get("has_date") else 0
            stats["egp"] += 1 if m.get("has_egp") else 0
            stats["company_ar"] += 1 if m.get("has_company_ar") else 0
        if stats["count"]:
            stats["avg_lines"] = round(stats["avg_lines"] / stats["count"], 1)
            out[bank] = stats
    return out

if __name__ == "__main__":
    import pprint
    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(summarize_quality())
