from awe_agentcheck.domain.gate import evaluate_medium_gate
from awe_agentcheck.domain.models import ReviewVerdict


def test_medium_gate_passes_when_all_checks_and_reviews_clear():
    outcome = evaluate_medium_gate(
        tests_ok=True,
        lint_ok=True,
        reviewer_verdicts=[ReviewVerdict.NO_BLOCKER, ReviewVerdict.NO_BLOCKER],
    )
    assert outcome.passed is True
    assert outcome.reason == 'passed'


def test_medium_gate_fails_when_any_blocker_exists():
    outcome = evaluate_medium_gate(
        tests_ok=True,
        lint_ok=True,
        reviewer_verdicts=[ReviewVerdict.NO_BLOCKER, ReviewVerdict.BLOCKER],
    )
    assert outcome.passed is False
    assert outcome.reason == 'review_blocker'
