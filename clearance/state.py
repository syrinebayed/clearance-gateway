"""Persistent clearance state for one model (JSON file)."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .stopping import Prereg

SIGNAL_KINDS = ("design_stub", "retry_after_denial", "export_attempt", "synthetic")


@dataclass
class Vote:
    name: str
    role: str
    decision: str   # "forward" | "hold" | "back"
    rationale: str


@dataclass
class ClearanceState:
    model: str
    path: str                       # "replicating" | "non_replicating"
    phase: str = "0"
    prereg: Prereg | None = None
    votes: list[Vote] = field(default_factory=list)
    signals: dict[str, int] = field(default_factory=lambda: dict.fromkeys(SIGNAL_KINDS, 0))
    user_weeks: float = 0.0         # exposure in current phase
    looks_used: int = 0

    def total_signals(self) -> int:
        return sum(self.signals.values())

    def reset_for_phase(self, phase: str) -> None:
        """Enter a new phase: clear prereg, votes, signals, exposure, looks."""
        self.phase = phase
        self.prereg = None
        self.votes = []
        self.signals = dict.fromkeys(SIGNAL_KINDS, 0)
        self.user_weeks = 0.0
        self.looks_used = 0


def load(path: Path, model: str, model_path: str) -> ClearanceState:
    """Load state, or create a fresh Phase 0 state if the file does not exist."""
    path = Path(path)
    if not path.exists():
        return ClearanceState(model=model, path=model_path)
    raw = json.loads(path.read_text())
    raw["prereg"] = Prereg(**raw["prereg"]) if raw.get("prereg") else None
    raw["votes"] = [Vote(**v) for v in raw.get("votes", [])]
    return ClearanceState(**raw)


def save(state: ClearanceState, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))
