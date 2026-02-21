from __future__ import annotations

from awe_agentcheck.event_analysis import extract_disputes, derive_next_steps


def test_extract_disputes_includes_proposal_consensus_stall_details():
    events = [
        {
            'type': 'proposal_consensus_stalled',
            'payload': {
                'stall_kind': 'in_round',
                'round': 1,
                'attempt': 3,
                'retry_limit': 3,
                'verdicts': {'no_blocker': 0, 'blocker': 1, 'unknown': 1},
            },
        }
    ]

    disputes = extract_disputes(events)
    assert disputes
    assert disputes[0]['participant'] == 'system'
    assert disputes[0]['verdict'] == 'consensus_stalled'
    assert 'round=1' in str(disputes[0]['note'])
    assert 'attempt=3/3' in str(disputes[0]['note'])


def test_derive_next_steps_for_waiting_manual_consensus_stall():
    steps = derive_next_steps(
        status='waiting_manual',
        reason='proposal_consensus_stalled_in_round',
        disputes=[{'participant': 'system', 'verdict': 'consensus_stalled', 'note': 'x'}],
    )
    assert steps
    assert 'Proposal discussion stalled' in steps[0]
