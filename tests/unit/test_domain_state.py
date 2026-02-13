import pytest

from awe_agentcheck.domain.models import TaskStatus, can_transition


@pytest.mark.parametrize(
    'from_status,to_status,expected',
    [
        (TaskStatus.QUEUED, TaskStatus.RUNNING, True),
        (TaskStatus.RUNNING, TaskStatus.PASSED, True),
        (TaskStatus.RUNNING, TaskStatus.FAILED_GATE, True),
        (TaskStatus.PASSED, TaskStatus.RUNNING, False),
    ],
)
def test_status_transition_rules(from_status, to_status, expected):
    assert can_transition(from_status, to_status) is expected
