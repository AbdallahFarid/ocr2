from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from app.config import DEFAULT_CONFIDENCE


@dataclass
class RouteDecision:
    decision: str  # "auto_approve" | "review"
    stp: bool
    low_conf_fields: List[str]
    reasons: List[str]
    overall_conf: float


def decide_route(
    per_field: Mapping[str, Mapping[str, Any]],
    *,
    required_fields: Sequence[str] = ("date", "amount_numeric", "cheque_number", "name"),
    threshold: Optional[float] = None,
) -> RouteDecision:
    """Decide routing based on field confidences and validations.

    per_field: mapping field -> { field_conf: float, validation?: { ok: bool, code?: str } }
    threshold: global threshold; if None, use DEFAULT_CONFIDENCE.global_threshold
    """
    thr = float(threshold if threshold is not None else DEFAULT_CONFIDENCE.global_threshold)

    low_conf: List[str] = []
    reasons: List[str] = []
    conf_values: List[float] = []

    for f in required_fields:
        rec = per_field.get(f, {})
        conf = float(rec.get("field_conf", 0.0))
        conf_values.append(conf)
        if conf < thr:
            low_conf.append(f)
            reasons.append(f"low_confidence:{f}:{conf:.3f}<thr{thr:.3f}")
        # If validation present, respect it
        v = rec.get("validation")
        if isinstance(v, Mapping):
            vok = bool(v.get("ok", True))
            if not vok:
                code = str(v.get("code") or "VALIDATION_FAIL")
                reasons.append(f"validation_failed:{f}:{code}")
    overall_conf = min(conf_values) if conf_values else 0.0
    stp = len(low_conf) == 0 and not any(r.startswith("validation_failed:") for r in reasons)
    decision = "auto_approve" if stp else "review"
    return RouteDecision(
        decision=decision,
        stp=stp,
        low_conf_fields=low_conf,
        reasons=reasons,
        overall_conf=overall_conf,
    )
