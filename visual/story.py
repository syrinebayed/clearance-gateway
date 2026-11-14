"""The guided story: what each step says, and which real gateway calls it makes.

Action kinds: tool (a gateway MCP tool call), reset (start again on a path), rare (set the
rare-event dot field), tamper (forge one entry in a copy of the audit log).
"""
from .cast import CRITERIA, IDENTITIES, RATIONALE, ROSTER, RULE


def _tool(tool: str, /, **args) -> dict:
    return {"kind": "tool", "tool": tool, "args": args}


def _who(role: str) -> dict:
    return _tool("whoami", name=IDENTITIES[role]["name"], role=role)


def _prereg(phase: str) -> dict:
    return _tool("preregister_phase", criteria=CRITERIA[phase], **RULE)


def _votes(role: str, decisions: list[str]) -> list[dict]:
    return [_tool("cast_gate_vote", evaluator_name=name, evaluator_role=role, decision=d, rationale=RATIONALE[d])
            for name, d in zip(ROSTER[role], decisions)]


def _rare(rate: float, detection: float) -> dict:
    return {"kind": "rare", "rate": rate, "detection": detection}


def _step(id: str, focus: str, title: str, caption: str, why: str = "", dwell: float = 5.0, actions=()) -> dict:
    return {"id": id, "focus": focus, "title": title, "caption": caption, "why": why,
            "dwell": dwell, "actions": list(actions)}


SEARCH = _tool("bio_search", entity="article", query="p53 tumor suppressor")
TP53 = _tool("bio_get", entity="gene", id="TP53")

STEPS: list[dict] = [
    _step("title", "ladder", "Contain, don't ban",
          "AI that can design biology should be released the way new drugs reach people: one containment "
          "phase at a time, with a rule agreed in advance for when to step back.",
          "This demo runs the real Clearance Gateway. Nothing here is a mock-up.", 6.0),
    _step("rare", "rare", "You cannot wait to see misuse",
          "If 1 user in 100,000 attempts misuse, you must watch about 300,000 users to be 95% sure of seeing "
          "one case. If monitoring catches only 6% of attempts, about 5 million.",
          "Drug regulators accept the same limit: trials are not expected to catch events rarer than about "
          "1 in 1,000 (ICH E1).", 4.0, [_rare(1e-3, 1.0), _rare(1e-5, 1.0), _rare(1e-5, 0.06)]),
    _step("ladder", "ladder", "So start contained, then widen",
          "The model starts in the tightest ring, an air-gapped BSL-4 lab. Each wider ring must be earned: "
          "BSL-3, then accredited individuals, then the public.",
          "A release is hard to undo. Containment keeps every step reversible.", 8.0),
    _step("criteria", "gate", "Criteria first, then votes",
          "A regulator opens Phase 0 and an evaluator tries to vote early. The gateway refuses: no vote "
          "counts until the pass criteria are written down.",
          "Pre-registration stops anyone from moving the goalposts after seeing the results.", 5.0,
          [_who("regulator"), _tool("cast_gate_vote", evaluator_name=ROSTER["regulator"][0],
                                    evaluator_role="regulator", decision="forward", rationale="Keen to move on")]),
    _step("prereg", "gate", "The rule is fixed in advance",
          "The regulator registers the criteria and a statistical stopping rule. The gateway reports how much "
          "exposure that rule needs before it can fire: about 2,382 user-weeks.",
          "Publishing the power calculation shows whether a rule can do its job.", 6.0, [_prereg("0")]),
    _step("signoff", "gate", "Five named sign-offs",
          "Five named evaluators each vote forward, hold or back. Three are needed to move. Four vote forward, "
          "so the model enters Phase 1.",
          "Named people, on the record. A split vote means hold, and hold is a legitimate answer.", 5.0,
          _votes("regulator", ["forward", "forward", "forward", "forward", "hold"])),
    _step("airgap", "flow", "Phase 1: no internet",
          "Inside the BSL-4 lab the agent asks for a literature search. The gateway refuses, and the BioMCP "
          "server behind it is never contacted.",
          "Same agent, same tools. Only the model's phase decides what gets through.", 5.0,
          [_who("bsl4_staff"), SEARCH]),
    _step("probe", "flow", "Probing is counted, not read",
          "The agent tries the same call again. That retry is counted as a signal. The gateway logs behaviour "
          "and never stores what was asked.",
          "Attackers split a task into innocent-looking pieces, so single requests look harmless. Patterns are "
          "harder to hide.", 6.0, [SEARCH]),
    _step("stub", "flow", "Design is a logged stub",
          "The design tool here is a stand-in. It returns a placeholder and a logged ID. No biological sequence "
          "is generated, shown or stored anywhere in this demo.",
          "Every design attempt is counted, cleared or not.", 5.0, [_tool("design_stub", purpose="demo")]),
    _step("gate1", "gate", "A split board still decides",
          "BSL-4 staff sign off the next gate: three forward, one hold, one back. Three is enough. The model "
          "moves out to Phase 2.",
          "The people who tested the model in containment are the ones who sign.", 4.5,
          [_who("regulator"), _prereg("1"),
           *_votes("bsl4_staff", ["forward", "forward", "forward", "hold", "back"])]),
    _step("bsl3", "flow", "Phase 2: a wider ring",
          "A BSL-3 scientist asks for a gene record. This time the request is cleared, and a real BioMCP record "
          "comes back through the gateway.",
          "BioMCP is unmodified. The gateway sits in front of it like a clearance desk.", 6.0,
          [_who("bsl3_staff"), TP53]),
    _step("export", "flow", "Designs stay in the container",
          "Sending a design outside is refused in every phase before full clearance, and each attempt is "
          "counted.", "", 4.5, [_tool("export_design", design_id="D-0001")]),
    _step("rule", "stopping", "A stopping rule, set before the data",
          "For Phase 2 the regulator fixes the numbers before monitoring starts: the normal signal rate, the "
          "rise that must be caught, and four scheduled looks.",
          "This is how a drug trial's safety board works: the boundary is drawn before anyone sees results.",
          7.0, [_who("regulator"), _prereg("2")]),
    _step("look1", "stopping", "Look 1: normal traffic",
          "After 1,000 user-weeks there are 2 signals, exactly what the baseline predicts. The p-value is 0.59, "
          "far from the 0.0125 threshold. The phase continues.", "", 6.5,
          [_tool("ingest_synthetic_traffic", user_weeks=1000, signals=1)]),
    _step("look2", "stopping", "Look 2: the rule fires",
          "Signals jump to 10 where 2.4 were expected. The p-value falls to 0.0002, the rule fires on its own, "
          "and the model steps back one phase.",
          "One phase back, not to zero. No meeting, no judgment call.", 8.0,
          [_tool("ingest_synthetic_traffic", user_weeks=200, signals=8)]),
    _step("regated", "flow", "Access is gone at once",
          "The same scientist repeats the same request. Denied: BSL-3 staff are not cleared while the model is "
          "back in BSL-4.",
          "Nobody had to remember to revoke anything.", 5.0, [_who("bsl3_staff"), TP53]),
    _step("power", "power", "A rule that can actually fire",
          "A rule that can never fire is theatre. This one has an 80% chance of catching a threefold rise in "
          "signals after about 2,382 user-weeks of use.",
          "Proxy signals are frequent and harmless, so the statistics work. Whether they track real misuse is "
          "the open research question.", 8.5),
    _step("audit", "audit", "Every step is on the record",
          "Each decision is a block that carries the fingerprint of the block before it. The gateway checks "
          "the whole chain: intact.", "", 5.5, [_tool("verify_audit")]),
    _step("tamper", "audit", "Try to rewrite history",
          "In a copy of the log, one past vote is changed from hold to forward. The chain breaks at exactly "
          "that block. The original is untouched.",
          "Tamper-evident records are what make named sign-offs worth trusting.", 7.0,
          [{"kind": "tamper", "mode": "edit"}]),
    _step("fast", "ladder", "A fast track for lower-risk models",
          "A model that cannot design self-replicating biology skips the BSL-4 ring. Regulators sign, and it "
          "moves straight from Phase 0 to Phase 2.",
          "Proportionate rules keep the gate credible. Here the path is declared by an expert panel, not "
          "tested.", 6.0,
          [{"kind": "reset", "path": "non_replicating"}, _who("regulator"), _prereg("0"),
           *_votes("regulator", ["forward"] * 5)]),
    _step("close", "ladder", "Contain, don't ban",
          "Staged release, criteria fixed in advance, named sign-offs, and a stopping rule that acts on its "
          "own. All of it ran live on the real gateway. Now try to break it.",
          "Switch to Sandbox to change role, call tools, cast votes and inject traffic.", 8.0),
]


def replay(session, upto: int) -> None:
    """Rebuild the state a viewer has after watching steps [0, upto). No network: upstream answers from memory."""
    session.reset()
    for step in STEPS[:upto]:
        for action in step["actions"]:
            if action["kind"] == "reset":
                session.reset(action["path"])
            elif action["kind"] == "tool":
                session.call(action["tool"], action["args"], fast=True)
