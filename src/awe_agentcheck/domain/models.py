from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    WAITING_MANUAL = 'waiting_manual'
    PASSED = 'passed'
    FAILED_GATE = 'failed_gate'
    FAILED_SYSTEM = 'failed_system'
    CANCELED = 'canceled'


class ReviewVerdict(str, Enum):
    NO_BLOCKER = 'no_blocker'
    BLOCKER = 'blocker'
    UNKNOWN = 'unknown'


_ALLOWED_TRANSITIONS = {
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELED},
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_MANUAL,
        TaskStatus.PASSED,
        TaskStatus.FAILED_GATE,
        TaskStatus.FAILED_SYSTEM,
        TaskStatus.CANCELED,
    },
    TaskStatus.WAITING_MANUAL: {TaskStatus.RUNNING, TaskStatus.CANCELED},
    TaskStatus.FAILED_GATE: {TaskStatus.RUNNING, TaskStatus.CANCELED},
    TaskStatus.FAILED_SYSTEM: {TaskStatus.RUNNING, TaskStatus.CANCELED},
    TaskStatus.PASSED: set(),
    TaskStatus.CANCELED: set(),
}


def can_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    return to_status in _ALLOWED_TRANSITIONS[from_status]
