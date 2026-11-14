"""Phase x role x tool policy from 'Contain, Don't Ban'. Pure data plus pure functions."""
from dataclasses import dataclass
from typing import Literal

Phase = Literal["0", "1", "2", "3", "public"]
Path = Literal["replicating", "non_replicating"]
Role = Literal["regulator", "bsl4_staff", "bsl3_staff", "accredited", "public"]
Tool = Literal["bio_search", "bio_get", "design_stub", "export_design"]

PHASE_NAMES: dict[str, str] = {
    "0": "Phase 0 (Certification, test environment)",
    "1": "Phase 1 (BSL-4, air-gapped)",
    "2": "Phase 2 (BSL-3, closed container with internet)",
    "3": "Phase 3 (Accredited individuals, closed container)",
    "public": "Full clearance (public, bio login for novel sequences)",
}

ROLES_BY_PHASE: dict[str, set[str]] = {
    "0": {"regulator"},
    "1": {"bsl4_staff"},
    "2": {"bsl4_staff", "bsl3_staff"},
    "3": {"bsl4_staff", "bsl3_staff", "accredited"},
    "public": {"bsl4_staff", "bsl3_staff", "accredited", "public"},
}

_P2_SEARCH = {"article", "trial", "gene", "protein"}
_P2_GET = {"gene", "article", "trial", "disease", "drug", "pathway", "protein"}
_P3_SEARCH = _P2_SEARCH | {"variant", "pgx", "gwas"}
_P3_GET = _P2_GET | {"variant", "pgx", "adverse-event", "cell-line"}
_ALL = {"*"}

ENTITIES_BY_PHASE: dict[tuple[str, str], set[str]] = {
    ("2", "bio_search"): _P2_SEARCH, ("2", "bio_get"): _P2_GET,
    ("3", "bio_search"): _P3_SEARCH, ("3", "bio_get"): _P3_GET,
    ("public", "bio_search"): _ALL, ("public", "bio_get"): _ALL,
}

PATH_ORDER: dict[str, list[str]] = {
    "replicating": ["0", "1", "2", "3", "public"],
    "non_replicating": ["0", "2", "3", "public"],
}

GATE_VOTER_ROLE: dict[str, str] = {"0": "regulator", "1": "bsl4_staff", "2": "bsl3_staff", "3": "accredited"}

DESIGN_PHASES = {"1", "2", "3", "public"}
BIO_ID_REQUIRED = {"3", "public"}
EXPORT_PHASES = {"public"}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str  # human-readable, names the rule; starts with "DENIED:" when not allowed


def _deny(reason: str) -> Decision:
    return Decision(False, f"DENIED: {reason}")


def _bio_data(phase: str, tool: str, entity: str | None) -> Decision:
    if phase == "1":
        return _deny(f"{PHASE_NAMES['1']}: no internet, live BioMCP not cleared")
    allowed = ENTITIES_BY_PHASE.get((phase, tool), set())
    if "*" in allowed or entity in allowed:
        return Decision(True, f"cleared: {tool}({entity}) in {PHASE_NAMES[phase]}")
    return _deny(f"{tool}({entity}) not cleared in {PHASE_NAMES[phase]}")


def _design(phase: str, has_bio_id: bool) -> Decision:
    if phase not in DESIGN_PHASES:
        return _deny(f"sequence design not cleared in {PHASE_NAMES[phase]}")
    if phase in BIO_ID_REQUIRED and not has_bio_id:
        return _deny("sequence design requires the shared bio login outside containment labs")
    return Decision(True, f"cleared (logged): design in {PHASE_NAMES[phase]}")


def _export(phase: str, has_bio_id: bool) -> Decision:
    if phase not in EXPORT_PHASES:
        return _deny(f"designs stay in the container in {PHASE_NAMES[phase]}")
    if not has_bio_id:
        return _deny("export requires the shared bio login")
    return Decision(True, "cleared (logged): export under full clearance")


def decide(phase: str, role: str, tool: str, entity: str | None, has_bio_id: bool) -> Decision:
    """Return whether this role may call this tool (and BioMCP entity) in this phase."""
    if role not in ROLES_BY_PHASE[phase]:
        return _deny(f"role '{role}' is not cleared to use the model in {PHASE_NAMES[phase]}")
    if tool in ("bio_search", "bio_get"):
        return _bio_data(phase, tool, entity)
    if tool == "design_stub":
        return _design(phase, has_bio_id)
    if tool == "export_design":
        return _export(phase, has_bio_id)
    return _deny(f"unknown tool '{tool}'")


def next_phase(path: str, phase: str) -> str | None:
    """Next phase on this path, or None if already at the end."""
    order = PATH_ORDER[path]
    i = order.index(phase)
    return order[i + 1] if i + 1 < len(order) else None


def prev_phase(path: str, phase: str) -> str:
    """Phase one step back on this path (Phase 0 stays at 0)."""
    order = PATH_ORDER[path]
    return order[max(order.index(phase) - 1, 0)]
