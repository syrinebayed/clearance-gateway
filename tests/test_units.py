"""Unit tests for the pure modules: redact, policy, audit, stopping, gates."""
import json

import pytest

from clearance import gates, policy
from clearance.audit import AuditLog
from clearance.redact import PLACEHOLDER, redact
from clearance.state import ClearanceState
from clearance.stopping import Prereg, check, poisson_sf, required_user_weeks


def _prereg(phase: str) -> Prereg:
    return Prereg(phase, "demo criteria", 0.002, 3.0, 0.05, 4, "Dr. Reg")


# --- redact ---------------------------------------------------------------

def test_redact_removes_long_nucleotide_run():
    # Covers: a 40-letter nucleotide run is replaced and counted.
    r = redact("x " + "ACGT" * 10 + " y")
    assert PLACEHOLDER in r.text and r.n_redacted == 1


def test_redact_leaves_english_and_gene_text():
    # Covers: ordinary prose (even words made of a/c/g/t/n) is not redacted.
    r = redact("a cat can at an act tan can a gnat. TP53 encodes p53.")
    assert r.n_redacted == 0


# --- policy ---------------------------------------------------------------

def test_phase1_air_gapped_blocks_biomcp_but_allows_design():
    # Covers: BSL-4 has no internet, so live BioMCP is denied; logged design is allowed.
    assert not policy.decide("1", "bsl4_staff", "bio_search", "article", False).allowed
    assert policy.decide("1", "bsl4_staff", "design_stub", None, False).allowed


def test_phase2_allows_listed_entities_and_blocks_export():
    # Covers: BSL-3 gets article search, not variant lookups; designs stay in the container.
    assert policy.decide("2", "bsl3_staff", "bio_search", "article", False).allowed
    assert not policy.decide("2", "bsl3_staff", "bio_get", "variant", False).allowed
    assert not policy.decide("2", "bsl3_staff", "export_design", None, True).allowed


def test_role_outside_phase_is_denied():
    # Covers: an accredited individual cannot use the model while it is in BSL-3.
    d = policy.decide("2", "accredited", "bio_get", "gene", False)
    assert not d.allowed and d.reason.startswith("DENIED:")


def test_phase3_design_requires_bio_login():
    # Covers: outside containment labs, sequence design needs the shared bio login.
    assert not policy.decide("3", "accredited", "design_stub", None, False).allowed
    assert policy.decide("3", "accredited", "design_stub", None, True).allowed


def test_fast_track_path_order():
    # Covers: non-replicating path jumps 0 -> 2, and steps back 2 -> 0.
    assert policy.next_phase("non_replicating", "0") == "2"
    assert policy.prev_phase("non_replicating", "2") == "0"


# --- audit ----------------------------------------------------------------

def test_audit_chain_detects_tampering(tmp_path):
    # Covers: editing a past vote breaks the hash chain at that entry.
    log = AuditLog(tmp_path / "a.jsonl")
    for d in ("forward", "hold", "back"):
        log.append("vote", decision=d)
    assert log.verify() == (True, None)
    lines = (tmp_path / "a.jsonl").read_text().splitlines()
    entry = json.loads(lines[1])
    entry["data"]["decision"] = "forward"
    lines[1] = json.dumps(entry, sort_keys=True)
    (tmp_path / "a.jsonl").write_text("\n".join(lines) + "\n")
    assert log.verify() == (False, 1)


# --- stopping -------------------------------------------------------------

def test_poisson_tail_matches_closed_form():
    # Covers: exact Poisson tail against hand-computed values.
    assert poisson_sf(3, 1.0) == pytest.approx(0.0803, abs=1e-4)
    assert poisson_sf(1, 0.05) == pytest.approx(0.04877, abs=1e-5)


def test_rule_fires_only_on_elevated_signals():
    # Covers: 2 signals at expected 2 does not fire; 9 does.
    p = _prereg("2")
    assert not check(p, 1000, 2, 1).fired
    assert check(p, 1000, 9, 2).fired


def test_power_calculation_is_finite_and_grows_with_smaller_effect():
    # Covers: detecting a smaller rise needs more exposure.
    big = required_user_weeks(_prereg("2"))
    small = required_user_weeks(Prereg("2", "c", 0.002, 1.5, 0.05, 4, "r"))
    assert 0 < big < small < float("inf")


# --- gates ----------------------------------------------------------------

def _vote_all(state, role, decisions):
    out = None
    for i, d in enumerate(decisions):
        out = gates.cast_vote(state, f"Evaluator {i}", role, d, "rationale")
    return out


def test_votes_refused_before_preregistration():
    # Covers: criteria must be registered before the phase starts.
    s = ClearanceState("m", "replicating")
    with pytest.raises(gates.GateError):
        gates.cast_vote(s, "Dr. A", "regulator", "forward", "r")


def test_three_forward_advances_and_resets_phase():
    # Covers: 3 of 5 forward moves to the next phase and clears prereg/votes.
    s = ClearanceState("m", "replicating")
    gates.preregister(s, _prereg("0"))
    out = _vote_all(s, "regulator", ["forward", "forward", "forward", "hold", "hold"])
    assert out.decision == "forward" and s.phase == "1" and s.prereg is None and s.votes == []


def test_split_vote_holds():
    # Covers: 2 forward, 2 hold, 1 back is a hold; phase unchanged, new round possible.
    s = ClearanceState("m", "replicating")
    gates.preregister(s, _prereg("0"))
    out = _vote_all(s, "regulator", ["forward", "forward", "hold", "hold", "back"])
    assert out.decision == "hold" and s.phase == "0" and s.votes == []


def test_three_back_steps_back_one_phase():
    # Covers: 3 of 5 back moves one phase back, not to zero.
    s = ClearanceState("m", "replicating", phase="2")
    gates.preregister(s, _prereg("2"))
    out = _vote_all(s, "bsl3_staff", ["back", "back", "back", "forward", "hold"])
    assert out.decision == "back" and s.phase == "1"


def test_wrong_role_and_duplicate_voter_refused():
    # Covers: only the phase's testers sign off, and each name votes once.
    s = ClearanceState("m", "replicating", phase="1")
    gates.preregister(s, _prereg("1"))
    with pytest.raises(gates.GateError):
        gates.cast_vote(s, "Dr. A", "bsl3_staff", "forward", "r")
    gates.cast_vote(s, "Dr. A", "bsl4_staff", "forward", "r")
    with pytest.raises(gates.GateError):
        gates.cast_vote(s, "Dr. A", "bsl4_staff", "forward", "r")


def test_fast_track_gate_goes_from_0_to_2():
    # Covers: non-replicating model signed off by regulator biologists skips BSL-4.
    s = ClearanceState("m", "non_replicating")
    gates.preregister(s, _prereg("0"))
    _vote_all(s, "regulator", ["forward"] * 5)
    assert s.phase == "2"
