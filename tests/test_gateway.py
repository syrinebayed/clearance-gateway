"""Integration tests for the gateway tools, with BioMCP replaced by a fake (plus one live test)."""
import asyncio
import socket
from pathlib import Path

import pytest

from clearance import gateway as gw
from clearance.redact import redact


class FakeProxy:
    def __init__(self):
        self.calls = []

    async def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        return f"fake {tool} result", False


@pytest.fixture
def rt(tmp_path):
    runtime = gw.configure(tmp_path, "demo-model", "replicating", "biomcp")
    runtime.proxy = FakeProxy()
    return runtime


def _advance(phase_role: str, prereg_baseline: float = 0.002):
    """Regulator pre-registers the current phase, then 5 named evaluators vote forward."""
    gw.whoami("Dr. Reg", "regulator")
    gw.preregister_phase("demo criteria", prereg_baseline, 3.0)
    for i in range(5):
        out = gw.cast_gate_vote(f"Evaluator {i}", phase_role, "forward", "criteria met")
    return out


def test_tools_require_identity(rt):
    # Covers: no identity, no access.
    assert gw.design_stub("x").startswith("DENIED: identify yourself")


def test_phase1_blocks_biomcp_and_never_calls_upstream(rt):
    # Covers: in BSL-4 the gateway refuses live BioMCP and BioMCP is never contacted.
    _advance("regulator")
    gw.whoami("Tech", "bsl4_staff")
    out = asyncio.run(gw.bio_search("article", query="p53"))
    assert out.startswith("DENIED:") and rt.proxy.calls == []


def test_retry_after_denial_is_a_signal(rt):
    # Covers: probing (repeating a denied call) is counted as a content-free signal.
    _advance("regulator")
    gw.whoami("Tech", "bsl4_staff")
    asyncio.run(gw.bio_search("article"))
    asyncio.run(gw.bio_search("article"))
    assert rt.state.signals["retry_after_denial"] == 1


def test_design_stub_never_returns_a_sequence(rt):
    # Covers: the only design capability is a stub; output contains no sequence-like text.
    _advance("regulator")
    gw.whoami("Tech", "bsl4_staff")
    out = gw.design_stub("anything")
    assert gw.STUB in out and redact(out).n_redacted == 0
    assert rt.state.signals["design_stub"] == 1


def test_denied_design_attempt_is_still_a_signal(rt):
    # Regression: an uncleared role probing sequence design must leave a proxy signal.
    gw.whoami("Tech", "bsl4_staff")
    assert gw.design_stub("x").startswith("DENIED:")
    assert rt.state.signals["design_stub"] == 1


def test_phase2_proxies_allowed_call_and_blocks_export(rt):
    # Covers: BSL-3 forwards cleared BioMCP calls; exporting a design is denied and counted.
    _advance("regulator")
    _advance("bsl4_staff")
    gw.whoami("Lab", "bsl3_staff")
    assert asyncio.run(gw.bio_get("gene", "TP53")) == "fake get result"
    assert gw.export_design("D-0001").startswith("DENIED:")
    assert rt.state.signals["export_attempt"] == 1


def test_stopping_rule_steps_back_and_regates_tools(rt):
    # Covers: elevated signals at a look trigger a clinical hold, one phase back, tools re-gated.
    _advance("regulator")
    _advance("bsl4_staff")
    gw.whoami("Dr. Reg", "regulator")
    gw.preregister_phase("phase 2 criteria", 0.002, 3.0)
    assert "Rule not fired" in gw.ingest_synthetic_traffic(1000, 2)
    out = gw.ingest_synthetic_traffic(0, 7)
    assert "STOPPING RULE FIRED" in out and rt.state.phase == "1"
    gw.whoami("Lab", "bsl4_staff")
    assert asyncio.run(gw.bio_search("article")).startswith("DENIED:")


def test_looks_capped_at_preregistered_number(rt):
    # Regression: once planned looks are used, further looks are refused so alpha is not inflated.
    _advance("regulator")
    gw.whoami("Dr. Reg", "regulator")
    gw.preregister_phase("phase 1 criteria", 0.002, 3.0, planned_looks=2)
    gw.ingest_synthetic_traffic(100, 0)
    gw.ingest_synthetic_traffic(100, 0)
    assert gw.ingest_synthetic_traffic(100, 0).startswith("REFUSED: all 2 pre-registered looks")
    assert rt.state.looks_used == 2


def test_audit_chain_intact_after_full_flow(rt):
    # Covers: every step of a full flow is logged and the hash chain verifies.
    _advance("regulator")
    gw.whoami("Tech", "bsl4_staff")
    gw.design_stub("x")
    assert gw.verify_audit().startswith("Audit chain intact")


BIOMCP = gw._default_biomcp()


def _online(host: str = "mygene.info", port: int = 443) -> bool:
    try:
        socket.create_connection((host, port), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not Path(BIOMCP).exists(), reason="biomcp not installed")
@pytest.mark.skipif(not _online(), reason="no internet: live BioMCP test skipped")
def test_live_biomcp_through_gateway(tmp_path):
    # Covers: a real BioMCP record (gene TP53) flows through the gateway once Phase 2 is cleared.
    gw.configure(tmp_path, "demo-model", "non_replicating", BIOMCP)
    _advance("regulator")
    gw.whoami("Lab", "bsl3_staff")
    out = asyncio.run(gw.bio_get("gene", "TP53"))
    assert "TP53" in out and not out.startswith("DENIED")
