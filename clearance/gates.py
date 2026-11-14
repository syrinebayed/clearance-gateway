"""Gate decisions: pre-registration, named 3-of-5 votes, forward / hold / back one."""
from collections import Counter
from dataclasses import dataclass

from .policy import GATE_VOTER_ROLE, PHASE_NAMES, next_phase, prev_phase
from .state import ClearanceState, Vote
from .stopping import Prereg

QUORUM = 5
MAJORITY = 3
DECISIONS = ("forward", "hold", "back")


class GateError(Exception):
    """Raised with a human-readable reason when a gate action is not allowed."""


@dataclass(frozen=True)
class GateOutcome:
    decision: str        # "forward" | "hold" | "back"
    from_phase: str
    to_phase: str
    tally: dict[str, int]


def preregister(state: ClearanceState, prereg: Prereg) -> None:
    """Register criteria for the current phase; refused if votes already exist."""
    if prereg.phase != state.phase:
        raise GateError(f"pre-registration is for phase {prereg.phase}, model is in {PHASE_NAMES[state.phase]}")
    if state.votes:
        raise GateError("criteria cannot change after voting has started")
    state.prereg = prereg


def _check_vote(state: ClearanceState, name: str, role: str, decision: str) -> None:
    if state.phase not in GATE_VOTER_ROLE:
        raise GateError(f"no gate after {PHASE_NAMES[state.phase]}")
    if state.prereg is None:
        raise GateError("criteria must be registered before the phase starts; no votes accepted yet")
    if decision not in DECISIONS:
        raise GateError(f"decision must be one of {', '.join(DECISIONS)}")
    required = GATE_VOTER_ROLE[state.phase]
    if role != required:
        raise GateError(f"this gate is signed off by '{required}', not '{role}'")
    if any(v.name == name for v in state.votes):
        raise GateError(f"{name} has already voted on this gate")


def _resolve(state: ClearanceState) -> GateOutcome:
    tally = Counter(v.decision for v in state.votes)
    origin = state.phase
    if tally["forward"] >= MAJORITY:
        decision, target = "forward", next_phase(state.path, origin)
    elif tally["back"] >= MAJORITY:
        decision, target = "back", prev_phase(state.path, origin)
    else:
        decision, target = "hold", origin
    if decision == "hold":
        state.votes = []
    else:
        state.reset_for_phase(target)
    return GateOutcome(decision, origin, target, {d: tally[d] for d in DECISIONS})


def cast_vote(state: ClearanceState, name: str, role: str, decision: str, rationale: str) -> GateOutcome | None:
    """Record a named vote. Returns the outcome when the 5th vote arrives, else None."""
    _check_vote(state, name, role, decision)
    state.votes.append(Vote(name, role, decision, rationale))
    return _resolve(state) if len(state.votes) == QUORUM else None


def step_back(state: ClearanceState) -> GateOutcome:
    """Clinical hold from the stopping rule: move back one phase."""
    origin = state.phase
    target = prev_phase(state.path, origin)
    state.reset_for_phase(target)
    return GateOutcome("back", origin, target, {})
