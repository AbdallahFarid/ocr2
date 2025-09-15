from app.ocr.locator import locate_fields


def test_fabmisr_locator_with_patterns_and_anchor():
    # Image size from provided samples
    image_shape = (677, 1677)  # (h, w)

    # Minimal OCR lines derived from samples (BATCH-7 .. BATCH-13)
    ocr_lines = [
        {"text": "FABMISR", "confidence": 1.0, "pos": [168, 74]},
        {"text": "31/May/2026", "confidence": 0.99, "pos": [1369, 62]},
        {"text": "No : 11637510", "confidence": 0.98, "pos": [736, 46]},
        {"text": "31,149.00", "confidence": 1.0, "pos": [1508, 284]},
        {"text": "Pay against this cheque to or the order of", "confidence": 0.99, "pos": [276, 208]},
        {"text": "شركة بالم هيلز للتعمير", "confidence": 0.99, "pos": [1010, 177]},
    ]

    results = locate_fields(
        image_shape=image_shape,
        bank_id="FABMISR",
        template_id="default",
        ocr_lines=ocr_lines,
    )

    assert set(["bank_name", "date", "cheque_number", "amount_numeric", "name"]).issubset(results.keys())

    # Patterns should drive these
    assert results["bank_name"]["method"] in ("region_regex", "template_roi")
    assert results["date"]["method"] in ("region_regex", "template_roi", "anchor_date_right")
    assert results["cheque_number"]["method"] in ("region_regex", "template_roi")
    assert results["amount_numeric"]["method"] in ("region_regex", "template_roi", "anchor_egp_right")

    # Name should be selected via pay_to anchor to the right
    assert results["name"]["method"] in ("anchor_payee_scored", "anchor_right_longest", "template_roi")

    # Basic bbox sanity
    for fld, rec in results.items():
        x1, y1, x2, y2 = rec["bbox"]
        assert 0 <= x1 < x2 <= image_shape[1]
        assert 0 <= y1 < y2 <= image_shape[0]
        assert 0.0 <= rec["confidence"] <= 1.0
