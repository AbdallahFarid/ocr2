from __future__ import annotations

from enum import Enum
from typing import List


class BankLabel(str, Enum):
    QNB = "QNB"
    FABMISR = "FABMISR"
    BANQUE_MISR = "BANQUE_MISR"
    CIB = "CIB"
    AAIB = "AAIB"
    NBE = "NBE"
    UNKNOWN = "UNKNOWN"


ALL_LABELS: List[str] = [e.value for e in BankLabel]


def is_valid_label(label: str) -> bool:
    return label in ALL_LABELS
