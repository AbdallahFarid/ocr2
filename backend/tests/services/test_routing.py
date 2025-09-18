from app.services.routing import decide_route


def test_decide_route_auto_approve():
    per_field = {
        "date": {"field_conf": 0.999, "validation": {"ok": True}},
        "amount_numeric": {"field_conf": 0.999, "validation": {"ok": True}},
        "cheque_number": {"field_conf": 0.999, "validation": {"ok": True}},
        "name": {"field_conf": 0.999, "validation": {"ok": True}},
    }
    d = decide_route(per_field, threshold=0.995)
    assert d.decision == "auto_approve"
    assert d.stp is True
    assert d.low_conf_fields == []
    assert d.overall_conf >= 0.995


def test_decide_route_review_due_to_low_conf():
    per_field = {
        "date": {"field_conf": 0.999, "validation": {"ok": True}},
        "amount_numeric": {"field_conf": 0.990, "validation": {"ok": True}},
        "cheque_number": {"field_conf": 0.999, "validation": {"ok": True}},
        "name": {"field_conf": 0.999, "validation": {"ok": True}},
    }
    d = decide_route(per_field, threshold=0.995)
    assert d.decision == "review"
    assert d.stp is False
    assert "amount_numeric" in d.low_conf_fields


def test_decide_route_review_due_to_validation_fail():
    per_field = {
        "date": {"field_conf": 0.999, "validation": {"ok": True}},
        "amount_numeric": {"field_conf": 0.999, "validation": {"ok": False, "code": "AMOUNT_NONPOS"}},
        "cheque_number": {"field_conf": 0.999, "validation": {"ok": True}},
        "name": {"field_conf": 0.999, "validation": {"ok": True}},
    }
    d = decide_route(per_field, threshold=0.995)
    assert d.decision == "review"
    assert any(r.startswith("validation_failed:amount_numeric") for r in d.reasons)
