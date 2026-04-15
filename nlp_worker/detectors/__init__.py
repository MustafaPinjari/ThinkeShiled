"""
Detectors package for NLP tender specification analysis.

Defines the shared ``DetectionResult`` dataclass used by all four detectors.

Requirements: 4.1, 5.1, 6.1, 7.1
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DetectionResult:
    """Result produced by a detector when a fraud signal is found.

    Attributes:
        flag_type: One of ``SPEC_TAILORING``, ``SPEC_COPY_PASTE``,
            ``SPEC_VAGUE_SCOPE``, ``SPEC_UNUSUAL_RESTRICTION``.
        severity: ``"HIGH"`` or ``"MEDIUM"``.
        score: Numeric confidence score in ``[0.0, 1.0]``.
        trigger_data: Detector-specific evidence dict stored in the
            ``RedFlag.trigger_data`` JSON field.
    """

    flag_type: str
    severity: str
    score: float
    trigger_data: dict = field(default_factory=dict)
