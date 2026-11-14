"""Stopping-rule views: look history from the audit log, the boundary, and the power curve.

Every number comes from clearance.stopping; this module only arranges it for the charts.
"""
from dataclasses import asdict
from functools import lru_cache

from clearance import stopping
from clearance.stopping import Prereg

from .cast import RULE

GRID = 96  # points per curve


@lru_cache(maxsize=64)
def required_user_weeks(prereg: Prereg) -> float:
    return stopping.required_user_weeks(prereg)


def prereg_view(prereg: Prereg) -> dict:
    return {**asdict(prereg), "alpha_per_look": prereg.alpha_per_look,
            "required_user_weeks": required_user_weeks(prereg)}


def demo_prereg(phase: str, **overrides: float) -> Prereg:
    """The illustrative rule used before anything is registered."""
    rule = {**RULE, **overrides}
    return Prereg(phase, "", rule["baseline_per_user_week"], rule["rate_ratio"],
                  rule["alpha"], int(rule["planned_looks"]), "")


def _prereg_from_audit(data: dict) -> Prereg:
    return Prereg(data["phase"], data["criteria"], data["baseline"], data["rate_ratio"],
                  data["alpha"], data["planned_looks"], data["by"])


def _look_view(data: dict, prereg: Prereg) -> dict:
    return {**data,
            "user_weeks": round(data["expected"] / prereg.baseline_per_user_week, 1),
            "alpha_per_look": prereg.alpha_per_look,
            "critical": stopping._critical_count(data["expected"], prereg.alpha_per_look)}


def rounds(entries: list[dict]) -> list[dict]:
    """One monitoring round per pre-registration, with the looks that ran under it."""
    out: list[tuple[Prereg, dict]] = []
    for entry in entries:
        if entry["event"] == "preregister":
            prereg = _prereg_from_audit(entry["data"])
            out.append((prereg, {"phase": prereg.phase, "prereg": prereg_view(prereg), "looks": [], "fired": False}))
        elif entry["event"] == "look" and out:
            prereg, view = out[-1]
            view["looks"].append(_look_view(entry["data"], prereg))
            view["fired"] = view["fired"] or entry["data"]["fired"]
    return [view for _, view in out]


def curves(prereg: Prereg, max_user_weeks: float) -> list[dict]:
    """Expected count, firing boundary and power on an even grid of exposure."""
    points = []
    for i in range(1, GRID + 1):
        user_weeks = max_user_weeks * i / GRID
        expected = prereg.baseline_per_user_week * user_weeks
        points.append({"user_weeks": round(user_weeks, 1), "expected": expected,
                       "critical": stopping._critical_count(expected, prereg.alpha_per_look),
                       "power": stopping._power(prereg, user_weeks)})
    return points


def preview(prereg: Prereg, user_weeks: float, observed: int, look: int) -> dict:
    """What a look would conclude, without running it (stopping.check is pure)."""
    verdict = asdict(stopping.check(prereg, user_weeks, observed, look))
    return {**verdict, "user_weeks": user_weeks,
            "critical": stopping._critical_count(verdict["expected"], prereg.alpha_per_look)}


def monitor_view(state, entries: list[dict]) -> dict:
    """Payload for the stopping-rule and power panels."""
    history = rounds(entries)
    prereg = state.prereg or (None if not history else _prereg_from_audit(_last_prereg(entries)))
    shown = prereg or demo_prereg(state.phase)
    furthest = max([look["user_weeks"] for r in history[-1:] for look in r["looks"]] + [state.user_weeks])
    max_user_weeks = max(required_user_weeks(shown) * 1.05, furthest * 1.15)
    return {
        "registered": prereg is not None,
        "active": state.prereg is not None,
        "prereg": prereg_view(shown),
        "round": history[-1] if history else None,
        "rounds": len(history),
        "current": {"phase": state.phase, "user_weeks": state.user_weeks,
                    "observed": state.total_signals(), "looks_used": state.looks_used},
        "max_user_weeks": round(max_user_weeks),
        "curve": curves(shown, max_user_weeks),
    }


def _last_prereg(entries: list[dict]) -> dict:
    return next(e["data"] for e in reversed(entries) if e["event"] == "preregister")
