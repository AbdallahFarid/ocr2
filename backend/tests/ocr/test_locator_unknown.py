from app.ocr.locator import locate_fields


def test_unknown_template_fallback_locates_core_fields():
    # Typical cheque shape (h, w)
    image_shape = (700, 1700)

    # Minimal synthetic OCR lines (unknown bank):
    ocr_lines = [
        {"text": "31/Jan/2026", "confidence": 0.98, "pos": [1350, 120]},
        {"text": "No : 99887766", "confidence": 0.97, "pos": [800, 60]},
        {"text": "21,116.00", "confidence": 0.99, "pos": [1500, 340]},
        {"text": "شركة عينة للاختبار", "confidence": 0.96, "pos": [1100, 210]},
        # Some distracting labels
        {"text": "AGAINST THIS CHEQUE", "confidence": 0.99, "pos": [200, 210]},
        {"text": "PAY TO", "confidence": 0.99, "pos": [120, 240]},
    ]

    results = locate_fields(
        image_shape=image_shape,
        bank_id="Random",  # No template exists; should use fallback
        template_id="default",
        ocr_lines=ocr_lines,
    )

    # Should contain at least the core fields
    assert "bank_name" in results
    assert "date" in results
    assert "cheque_number" in results
    assert "amount_numeric" in results
    assert "name" in results

    # Methods should indicate fallback
    assert results["bank_name"]["method"] == "unknown_bank"
    assert results["date"]["method"] == "unknown_regex"
    assert results["amount_numeric"]["method"] == "unknown_regex"
    assert results["cheque_number"]["method"] == "unknown_regex"
    assert results["name"]["method"] in ("unknown_payee", "anchor_payee_scored")

    # Bbox sanity
    h, w = image_shape
    for rec in results.values():
        x1, y1, x2, y2 = rec["bbox"]
        assert 0 <= x1 < x2 <= w
        assert 0 <= y1 < y2 <= h
        assert 0.0 <= float(rec.get("confidence", 0.0)) <= 1.0
