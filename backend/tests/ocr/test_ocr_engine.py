import numpy as np
import pytest

from app.ocr.ocr_engine import PaddleOCREngine, OCRLine


def _poly(x=0, y=0, w=10, h=10):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _blank_image(w=100, h=60):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_parse_results_filters_by_conf_new_format():
    eng = PaddleOCREngine(use_angle_cls=False)
    results = [
        {
            "rec_texts": ["low", "HIGH"],
            "rec_scores": [0.2, 0.95],
            "rec_polys": [
                _poly(0, 0, 10, 10),
                _poly(10, 10, 10, 10),
            ],
        }
    ]
    lines = eng._parse_results(results, lang="en", min_confidence=0.3)
    assert len(lines) == 1
    assert lines[0].text == "HIGH"
    assert lines[0].lang == "en"
    assert 0.9 <= lines[0].confidence <= 1.0


def test_ocr_image_merges_langs_with_mixed_result_formats(monkeypatch):
    class StubOCREngineEn:
        def ocr(self, img):
            return [[(_poly(), ("EN-TEXT", 0.9))]]

    class StubOCREngineAr:
        def ocr(self, img):
            return [
                {
                    "rec_texts": ["AR-TEXT"],
                    "rec_scores": [0.95],
                    "rec_polys": [_poly()],
                }
            ]

    eng = PaddleOCREngine(use_angle_cls=False)

    def fake_get_engine(self, lang: str):
        return StubOCREngineEn() if lang == "en" else StubOCREngineAr()

    monkeypatch.setattr(PaddleOCREngine, "_get_engine", fake_get_engine, raising=True)

    img = _blank_image()
    lines = eng.ocr_image(img, languages=("en", "ar"), min_confidence=0.3)
    texts = {l.text for l in lines}
    langs = {l.lang for l in lines}
    assert "EN-TEXT" in texts and "AR-TEXT" in texts
    assert "en" in langs and "ar" in langs


def test_ocr_roi_selects_best_vote_by_avg_conf(monkeypatch):
    eng = PaddleOCREngine(use_angle_cls=False)
    call_counter = {"n": 0}

    best_vote_lines = [
        OCRLine(
            text="best1",
            raw_text="best1",
            confidence=0.8,
            bbox=_poly(),
            center=(5.0, 5.0),
            lang="en",
            engine="paddle",
        ),
        OCRLine(
            text="best2",
            raw_text="best2",
            confidence=0.7,
            bbox=_poly(),
            center=(6.0, 6.0),
            lang="en",
            engine="paddle",
        ),
    ]

    low_vote_lines = [
        OCRLine(
            text="low",
            raw_text="low",
            confidence=0.4,
            bbox=_poly(),
            center=(1.0, 1.0),
            lang="en",
            engine="paddle",
        )
    ]

    def fake_ocr_image(self, crop, languages=("en", "ar"), min_confidence=0.3):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            return low_vote_lines
        elif call_counter["n"] == 2:
            return best_vote_lines
        else:
            return []

    # Patch instance method
    monkeypatch.setattr(PaddleOCREngine, "ocr_image", fake_ocr_image, raising=True)

    img = _blank_image(100, 60)
    roi = (10, 10, 40, 40)
    lines = eng.ocr_roi(img, roi=roi, languages=("en",), min_confidence=0.3, padding=2, n_votes=3)

    texts = [l.text for l in lines]
    assert texts == ["best1", "best2"]
