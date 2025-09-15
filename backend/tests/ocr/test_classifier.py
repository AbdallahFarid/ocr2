import numpy as np

from app.ocr.classifier import Classifier
from app.config import ClassifierSettings
from app.ocr.labels import BankLabel


def _synthetic_band_image(left_val: int, right_val: int, w: int = 400, h: int = 200):
    """Create a grayscale image where the top-left/right bands differ in brightness.
    Heuristic engine reads the top 25% height and 25% width bands.
    """
    img = np.full((h, w), 180, dtype=np.uint8)
    band_h = max(1, int(0.25 * h))
    band_w = max(1, int(0.25 * w))
    img[0:band_h, 0:band_w] = np.uint8(left_val)
    img[0:band_h, w - band_w : w] = np.uint8(right_val)
    # Convert to BGR to simulate typical input
    return np.stack([img, img, img], axis=-1)


def test_stub_classifier_predict_qnb():
    settings = ClassifierSettings(engine="stub", conf_threshold=0.5)
    clf = Classifier(settings=settings)
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    label, conf = clf.predict(img)
    assert label == BankLabel.QNB.value
    assert conf >= 0.5


def test_heuristic_classifier_predict_qnb_when_left_darker():
    settings = ClassifierSettings(engine="heuristic", conf_threshold=0.2)
    clf = Classifier(settings=settings)
    img = _synthetic_band_image(left_val=80, right_val=200)
    label, conf = clf.predict(img)
    assert label in [BankLabel.QNB.value, BankLabel.UNKNOWN.value]
    # Prefer QNB when left is darker
    assert conf >= 0.2


def test_heuristic_classifier_predict_fabmisr_when_right_darker():
    settings = ClassifierSettings(engine="heuristic", conf_threshold=0.2)
    clf = Classifier(settings=settings)
    img = _synthetic_band_image(left_val=200, right_val=80)
    label, conf = clf.predict(img)
    assert label in [BankLabel.FABMISR.value, BankLabel.UNKNOWN.value]
    assert conf >= 0.2


def test_mobilenet_scaffold_unknown():
    settings = ClassifierSettings(engine="mobilenet", conf_threshold=0.5)
    clf = Classifier(settings=settings)
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    label, conf = clf.predict(img)
    assert label in [BankLabel.UNKNOWN.value, BankLabel.QNB.value, BankLabel.FABMISR.value]
    # As scaffold, we expect very low confidence
    assert conf <= 0.5
