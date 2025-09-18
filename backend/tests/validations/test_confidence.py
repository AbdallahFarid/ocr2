from app.validations.confidence import compute_field_confidence, passes_global_threshold


def test_compute_field_confidence_basic_ok():
    # Perfect OCR and locator, parse ok
    c = compute_field_confidence(1.0, 1.0, True)
    assert 0.999 <= c <= 1.0


def test_compute_field_confidence_parse_fail_factor():
    c = compute_field_confidence(0.9, 0.8, False, parse_fail_factor=0.5)
    assert abs(c - (0.9 * 0.8 * 0.5)) < 1e-6


def test_passes_global_threshold_default():
    # Using default global threshold ~0.995
    c = compute_field_confidence(1.0, 0.996, True)
    assert passes_global_threshold(c) is True
    c2 = compute_field_confidence(1.0, 0.990, True)
    assert passes_global_threshold(c2) is False
