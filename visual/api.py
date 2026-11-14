"""JSON API for the visual demo. Each handler is a thin view over the real gateway session."""
from clearance import policy
from clearance.audit import GENESIS

from . import cast, monitor, snapshot, stats, story
from .session import TAMPER_COPY, Session
from .tamper import MODES, tamper_copy


class Api:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.routes = {
            ("GET", "/api/state"): self._state,
            ("GET", "/api/policy"): self._policy,
            ("GET", "/api/tools"): self._tools,
            ("GET", "/api/looks"): self._looks,
            ("GET", "/api/looks/preview"): self._preview,
            ("GET", "/api/power"): self._power,
            ("GET", "/api/rare"): self._rare,
            ("GET", "/api/audit"): self._audit,
            ("GET", "/api/story"): self._story,
            ("POST", "/api/call"): self._call,
            ("POST", "/api/reset"): self._reset,
            ("POST", "/api/tamper"): self._tamper,
            ("POST", "/api/story/goto"): self._goto,
        }

    def handle(self, method: str, path: str, query: dict | None = None, body: dict | None = None) -> tuple[int, dict]:
        """Run one request. Returns (HTTP status, JSON payload)."""
        handler = self.routes.get((method, path))
        if handler is None:
            return 404, {"error": f"no such endpoint: {method} {path}"}
        try:
            with self.session.lock:
                return 200, handler(query or {}, body or {})
        except (ValueError, KeyError, TypeError) as exc:
            return 400, {"error": str(exc)}

    # --- read ---------------------------------------------------------------

    def _state(self, query: dict, body: dict) -> dict:
        return self.session.state()

    def _policy(self, query: dict, body: dict) -> dict:
        return {"ladders": {path: snapshot.ladder(path) for path in policy.PATH_ORDER},
                "paths": policy.PATH_ORDER, "roles": list(snapshot.ROLES), "tools": list(snapshot.TOOLS),
                "entities": snapshot.ENTITIES, "identities": cast.IDENTITIES, "bio_login": cast.BIO_LOGIN,
                "roster": cast.ROSTER, "rationale": cast.RATIONALE, "criteria": cast.CRITERIA,
                "rule": cast.RULE, "tamper_modes": list(MODES)}

    def _tools(self, query: dict, body: dict) -> dict:
        return {"tools": self.session.tools()}

    def _looks(self, query: dict, body: dict) -> dict:
        rt = self.session.rt
        return monitor.monitor_view(rt.state, rt.audit.entries())

    def _preview(self, query: dict, body: dict) -> dict:
        state = self.session.rt.state
        if state.prereg is None:
            raise ValueError("no stopping rule registered for this phase")
        view = monitor.preview(state.prereg, state.user_weeks + float(query.get("user_weeks", 0)),
                               state.total_signals() + int(query.get("signals", 0)), state.looks_used + 1)
        return {**view, "looks_left": state.prereg.planned_looks - state.looks_used}

    def _power(self, query: dict, body: dict) -> dict:
        state = self.session.rt.state
        overrides = {k: float(query[k]) for k in cast.RULE if k in query}
        prereg = state.prereg if state.prereg and not overrides else monitor.demo_prereg(state.phase, **overrides)
        if not (0.0005 <= prereg.baseline_per_user_week <= 0.05 and 1.5 <= prereg.rate_ratio <= 10
                and 0.005 <= prereg.alpha <= 0.2 and 1 <= prereg.planned_looks <= 8):
            raise ValueError("need baseline 0.0005..0.05, rate_ratio 1.5..10, alpha 0.005..0.2, planned_looks 1..8")
        needed = monitor.required_user_weeks(prereg)
        return {"prereg": monitor.prereg_view(prereg), "registered": state.prereg is not None and not overrides,
                "required_user_weeks": needed, "target_power": 0.8,
                "exposure": state.user_weeks, "curve": monitor.curves(prereg, needed * 1.6)}

    def _rare(self, query: dict, body: dict) -> dict:
        return stats.rare_event_view(float(query.get("rate", 1e-5)), float(query.get("detection", 1.0)))

    def _audit(self, query: dict, body: dict) -> dict:
        audit = self.session.rt.audit
        ok, broken_at = audit.verify()
        return {"entries": audit.entries(), "ok": ok, "broken_at": broken_at, "genesis": GENESIS}

    def _story(self, query: dict, body: dict) -> dict:
        return {"steps": story.STEPS}

    # --- act ----------------------------------------------------------------

    def _call(self, query: dict, body: dict) -> dict:
        result = self.session.call(body["tool"], body.get("args") or {})
        return {**result, "state": self.session.state()}

    def _reset(self, query: dict, body: dict) -> dict:
        self.session.reset(body.get("path", "replicating"))
        return self.session.state()

    def _tamper(self, query: dict, body: dict) -> dict:
        audit = self.session.rt.audit
        return tamper_copy(audit.path, self.session.data_dir / TAMPER_COPY, body.get("index"), body.get("mode", "edit"))

    def _goto(self, query: dict, body: dict) -> dict:
        index = int(body.get("index", 0))
        if not 0 <= index < len(story.STEPS):
            raise ValueError(f"step index must be between 0 and {len(story.STEPS) - 1}")
        story.replay(self.session, index)
        return self.session.state()
