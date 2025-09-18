"""OCR package.

Exports the OCR facade and related classes for external use.
"""

from .ocr_engine import PaddleOCREngine, MICREngine, OCRLine

__all__ = [
    "PaddleOCREngine",
    "MICREngine",
    "OCRLine",
]
