from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from awe_agentcheck.domain.models import ReviewVerdict


@dataclass(frozen=True)
class GateOutcome:
    passed: bool
    reason: str


def evaluate_medium_gate(*, tests_ok: bool, lint_ok: bool, reviewer_verdicts: Iterable[ReviewVerdict]) -> GateOutcome:
    verdicts = list(reviewer_verdicts)
    if not tests_ok:
        return GateOutcome(passed=False, reason='tests_failed')
    if not lint_ok:
        return GateOutcome(passed=False, reason='lint_failed')
    if any(v == ReviewVerdict.BLOCKER for v in verdicts):
        return GateOutcome(passed=False, reason='review_blocker')
    if any(v == ReviewVerdict.UNKNOWN for v in verdicts):
        return GateOutcome(passed=False, reason='review_unknown')
    if not verdicts:
        return GateOutcome(passed=False, reason='review_missing')
    return GateOutcome(passed=True, reason='passed')
