"""Read-only JSON views of the real gateway state and policy tables."""
from collections import Counter
from dataclasses import asdict

from clearance import gates, policy
from clearance.audit import GENESIS
from clearance.gateway import ROLES

from . import monitor
from .cast import ZONES

TOOLS = ("bio_search", "bio_get", "design_stub", "export_design")
PROBE_ENTITY = "gene"  # a BioMCP entity that both bio tools clear from Phase 2 on
ENTITIES = sorted(set().union(*policy.ENTITIES_BY_PHASE.values()) - {"*"})


def _entity(tool: str) -> str | None:
    return PROBE_ENTITY if tool.startswith("bio_") else None


def _cell(phase: str, role: str, tool: str) -> str:
    """cleared, bio_login (cleared only with the shared bio login), or denied."""
    if policy.decide(phase, role, tool, _entity(tool), False).allowed:
        return "cleared"
    if policy.decide(phase, role, tool, _entity(tool), True).allowed:
        return "bio_login"
    return "denied"


def access(phase: str) -> dict[str, dict[str, str]]:
    """Who may call what in this phase, straight from policy.decide."""
    return {role: {tool: _cell(phase, role, tool) for tool in TOOLS} for role in ROLES}


def _tool_rules(phase: str) -> dict[str, dict]:
    """Per-tool rule for a role that is cleared in this phase, with the allowed BioMCP entities."""
    role = next(r for r in ROLES if r in policy.ROLES_BY_PHASE[phase])
    rules = {}
    for tool in TOOLS:
        rule = {"state": _cell(phase, role, tool),
                "reason": policy.decide(phase, role, tool, _entity(tool), False).reason}
        if tool.startswith("bio_"):
            rule["entities"] = [e for e in ENTITIES if policy.decide(phase, role, tool, e, False).allowed]
            rule["all_entities"] = "*" in policy.ENTITIES_BY_PHASE.get((phase, tool), ())
        rules[tool] = rule
    return rules


def ladder(path: str) -> list[dict]:
    """All five phases with their rules; on_path is False for a phase this path skips."""
    order = policy.PATH_ORDER[path]
    return [{"id": phase, "name": policy.PHASE_NAMES[phase], "zone": ZONES[phase][0], "detail": ZONES[phase][1],
             "on_path": phase in order, "roles": [r for r in ROLES if r in policy.ROLES_BY_PHASE[phase]],
             "signed_by": policy.GATE_VOTER_ROLE.get(phase), "tools": _tool_rules(phase)}
            for phase in policy.PHASE_NAMES]


def _gate(state) -> dict:
    tally = Counter(v.decision for v in state.votes)
    return {"signed_by": policy.GATE_VOTER_ROLE.get(state.phase), "quorum": gates.QUORUM,
            "majority": gates.MAJORITY, "votes": [asdict(v) for v in state.votes],
            "tally": {d: tally[d] for d in gates.DECISIONS},
            "next_phase": policy.next_phase(state.path, state.phase),
            "prev_phase": policy.prev_phase(state.path, state.phase)}


def snapshot(rt, upstream) -> dict:
    """Everything the page needs to draw the current moment."""
    state = rt.state
    entries = rt.audit.entries()
    ok, broken_at = rt.audit.verify()
    return {
        "model": state.model, "path": state.path, "path_order": policy.PATH_ORDER[state.path],
        "phase": state.phase, "phase_name": policy.PHASE_NAMES[state.phase],
        "who": dict(rt.who) or None,
        "access": access(state.phase),
        "prereg": monitor.prereg_view(state.prereg) if state.prereg else None,
        "gate": _gate(state),
        "signals": dict(state.signals), "signals_total": state.total_signals(),
        "user_weeks": state.user_weeks, "looks_used": state.looks_used,
        "audit": {"ok": ok, "broken_at": broken_at, "count": len(entries),
                  "head": entries[-1]["hash"] if entries else GENESIS},
        "upstream": {"live": upstream.live is not None, "reached": upstream.reached, "last": upstream.last},
    }
