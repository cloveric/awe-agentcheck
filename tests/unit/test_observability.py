from __future__ import annotations

from awe_agentcheck.observability import configure_observability


def test_configure_observability_no_endpoint_is_noop():
    configure_observability(service_name='awe-agentcheck', otlp_endpoint=None)
