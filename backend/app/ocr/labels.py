from __future__ import annotations

from enum import Enum
from typing import List


class BankLabel(str, Enum):
    QNB = "QNB"
    FABMISR = "FABMISR"
    UNKNOWN = "UNKNOWN"


ALL_LABELS: List[str] = [e.value for e in BankLabel]


def is_valid_label(label: str) -> bool:
    return label in ALL_LABELS
