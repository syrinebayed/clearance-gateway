# Clearance Gateway

This is the working prototype for the policy proposal **"Contain, Don't Ban: Phased Clearance for AI That Designs Self-Replicating Biology."** The proposal treats a bio-capable AI model like a drug in clinical trials. It starts in a BSL-4 lab, moves to BSL-3, then to accredited individuals, then to the public. It moves only when pre-registered criteria are met and named evaluators sign off, and it steps back when a pre-registered stopping rule fires. The Clearance Gateway is an MCP server that enforces those rules live. It sits between an AI agent (such as Claude) and an unmodified [BioMCP](https://github.com/genomoncology/biomcp) server. Every tool call is checked against the model's current phase, the caller's role, and the tool. Every decision goes into a tamper-evident audit log.

## Architecture

```
Claude ──MCP──► Clearance Gateway ──MCP──► BioMCP (unmodified; only `search` and `get` forwarded)
                  │
                  ├─ policy:   phase × role × tool × BioMCP entity → allow, or "DENIED: <rule>"
                  ├─ gates:    pre-registered criteria, 5 named votes, 3 needed: forward / hold / back one
                  ├─ stopping: Poisson rule on content-free proxy signals → automatic step back one phase
                  ├─ redact:   strips long nucleotide / amino-acid strings from BioMCP output
                  └─ audit:    append-only JSON lines, SHA-256 hash chain
```

| File | Role |
|---|---|
| `clearance/gateway.py` | The MCP server and its 10 tools |
| `clearance/policy.py` | Phase, role, tool and entity tables; the `decide()` function |
| `clearance/gates.py` | Pre-registration and 3-of-5 votes |
| `clearance/stopping.py` | Poisson stopping rule and power calculation (stdlib only) |
| `clearance/state.py` | Per-model state, saved to `<data-dir>/state.json` |
| `clearance/audit.py` | Hash-chained log at `<data-dir>/audit.jsonl` |
| `clearance/redact.py` | Sequence redaction filter |
| `clearance/biomcp_proxy.py` | MCP client to `biomcp serve` |

## How it maps to the proposal

| Proposal | Gateway behaviour |
|---|---|
| Phase 0: Certification (test environment) | Only `regulator` may use the model. Criteria must be registered before any vote. Regulators sign off. |
| Phase 1: BSL-4, air-gapped | Only `bsl4_staff`. Live BioMCP is refused (no internet). Design is a logged stub. `bsl4_staff` sign off. |
| Phase 2: BSL-3, closed container with internet | Adds `bsl3_staff`. BioMCP search: article, trial, gene, protein. BioMCP get: those plus disease, drug, pathway. Export refused. `bsl3_staff` sign off. |
| Phase 3: Accredited individuals | Adds `accredited`. Search adds variant, pgx, gwas. Get adds variant, pgx, adverse-event, cell-line. Design needs the bio login. Export refused. `accredited` sign off. |
| Full clearance (public) | Adds `public`. All BioMCP entities. Design and export need the bio login. No further gate. |
| Fast track (non-replicating) | Started with `--path non_replicating`, the model goes 0 → 2 → 3 → public, skipping BSL-4. Stepping back from 2 goes to 0. |
| Named tester sign-off | `cast_gate_vote`: each named evaluator votes once; the vote resolves at 5 votes. |
| Three outcomes | 3 forward: next phase. 3 back: one phase back (never straight to zero). Anything else: hold, votes clear, criteria stay. |
| Pre-registration | `preregister_phase` (regulator only). Criteria cannot change once voting starts. Entering a new phase clears criteria, votes, signals and exposure. |
| Signals, not confirmed misuse | Counts behaviour, never content: design attempts (cleared or not), repeat calls to a tool that was already denied, export attempts, plus synthetic population traffic. |
| Stopping rule (DSMB look) | One-sided Poisson test of signals against baseline × user-weeks. Alpha is split evenly across planned looks (Pocock-style). If it fires: clinical hold, back one phase. Once all planned looks are used, further looks are refused until the board votes, so the false-alarm budget cannot be exceeded. |
| Published power calculation | `preregister_phase` and `clearance_status` report the user-weeks needed for 80% power: about 2,382 at the demo settings (baseline 0.002 per user-week, rate ratio 3, alpha 0.05, 4 looks). |
| One shared bio login | `whoami(..., bio_id=...)`. The ID is required for design in Phase 3 and public, and for export in public. It is a plain string; nothing checks it. |

## Safety design

- **No sequences, ever.** `design_stub` returns a fixed placeholder and a design ID (`D-0001`, ...). Nothing in this repo generates, requests or stores biological sequences.
- **Read-only upstream.** Only BioMCP's `search` and `get` tools are forwarded. BioMCP's other tools, including its general `biomcp` command tool, are not exposed.
- **Defense in depth.** All BioMCP output passes through a redaction filter. Nucleotide runs of 30+ letters and amino-acid runs of 50+ letters become `[REDACTED-SEQUENCE]`.
- **Content-free monitoring.** Tool-call audit entries record the tool, BioMCP entity, role, bio login, phase and verdict. They never record query text. Signals are counts only.
- **Synthetic traffic.** Population-scale exposure and signals come from `ingest_synthetic_traffic`. Real-world capability evidence is cited in the paper, not reproduced here.

## Setup

Requires Python 3.10+ (tested on 3.14) and internet access for the live BioMCP calls. Run everything from `clearance-gateway/`.

```bash
cd clearance-gateway
```

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

This installs `mcp`, `pytest` and BioMCP. BioMCP's PyPI package is `biomcp-cli` (not `biomcp`); it puts a `biomcp` binary in `.venv/bin/`.

### Run the tests

```bash
.venv/bin/python -m pytest -q
```

Expected: `27 passed`. One test (`test_live_biomcp_through_gateway`) calls the real BioMCP for gene TP53. It is skipped if BioMCP is not installed or there is no internet, so offline runs report `26 passed, 1 skipped`.

### Run the scripted demo

```bash
.venv/bin/python demo.py
```

It starts the gateway as a real MCP server over stdio and drives it the way Claude would. State goes to `demo_run/`, which is wiped at the start of each run. The last line should be `Audit chain intact (30 entries).` Add a number to pause between steps, for example `.venv/bin/python demo.py 1.5`.

### Use it from Claude Code

`.mcp.json` is gitignored because it holds absolute paths. Create it once from inside `clearance-gateway/`:

```bash
.venv/bin/python -c 'import json,os; h=os.getcwd(); json.dump({"mcpServers":{"clearance-gateway":{"command":h+"/.venv/bin/python","args":["-m","clearance.gateway","--model","demo-model","--path","replicating","--data-dir",h+"/run","--biomcp",h+"/.venv/bin/biomcp"],"env":{"PYTHONPATH":h}}}},open(".mcp.json","w"),indent=2)'
```

Or write it by hand from this template, replacing `<ABSOLUTE_PATH_TO_REPO>`:

```json
{
  "mcpServers": {
    "clearance-gateway": {
      "command": "<ABSOLUTE_PATH_TO_REPO>/clearance-gateway/.venv/bin/python",
      "args": ["-m", "clearance.gateway",
               "--model", "demo-model",
               "--path", "replicating",
               "--data-dir", "<ABSOLUTE_PATH_TO_REPO>/clearance-gateway/run",
               "--biomcp", "<ABSOLUTE_PATH_TO_REPO>/clearance-gateway/.venv/bin/biomcp"],
      "env": { "PYTHONPATH": "<ABSOLUTE_PATH_TO_REPO>/clearance-gateway" }
    }
  }
}
```

Then run `claude` in `clearance-gateway/`.

- Approve the `clearance-gateway` server when Claude Code asks.
- Allow `preregister_phase` and `cast_gate_vote` when prompted. Auto-mode safety classifiers may block these two tools because they change clearance state; approve them yourself.
- State persists in `run/` across restarts. Delete `run/` to start again from Phase 0.
- Use `--path non_replicating` in `.mcp.json` to try the fast track.

Try:

- *"Use whoami as Dr. Regulator, role regulator, then show clearance_status."*
- *"Pre-register Phase 0 with baseline 0.002 and rate ratio 3, then cast five named regulator votes: four forward, one hold."*
- *"Now whoami as a BSL-4 tech, role bsl4_staff, and search BioMCP articles on p53."* This is refused: Phase 1 is air-gapped.

## Demo (3 minutes)

This is what `demo.py` does, step by step.

1. **Phase 0.** The regulator signs in. A vote cast before criteria exist is refused. The regulator pre-registers criteria; the gateway reports about 2,382 user-weeks needed for 80% power. Five named regulators vote (4 forward, 1 hold): **GATE FORWARD** to Phase 1.
2. **Phase 1 (BSL-4).** A `bsl4_staff` tech searches BioMCP: **DENIED**, no internet. The same call again is denied and counted as a retry signal. `design_stub` returns the placeholder and `design_id=D-0001`.
3. **Phase 1 gate.** The regulator pre-registers Phase 1 criteria. Five named `bsl4_staff` evaluators vote 3 forward, 1 hold, 1 back: **GATE FORWARD** to Phase 2.
4. **Phase 2 (BSL-3).** A `bsl3_staff` scientist gets the real TP53 gene record from BioMCP through the gateway. Exporting `D-0001` is **DENIED**: designs stay in the container.
5. **DSMB look.** The regulator pre-registers the Phase 2 stopping rule. Look 1 (1,000 synthetic user-weeks, quiet traffic) does not fire. Look 2 (a spike in signals) gives p ≈ 0.0002 against a per-look threshold of 0.0125: **STOPPING RULE FIRED**, clinical hold, back to Phase 1.
6. **Re-gated.** The same BSL-3 scientist asks for TP53 again: **DENIED**, `bsl3_staff` is not cleared in Phase 1.
7. **Record.** `clearance_status` shows Phase 1 with fresh counters. `verify_audit` reports `Audit chain intact (30 entries).`

## Tools

| Tool | Arguments | What it does |
|---|---|---|
| `whoami` | `name, role, bio_id=""` | Sets who is using the model. Role is one of `regulator`, `bsl4_staff`, `bsl3_staff`, `accredited`, `public`. Resets retry tracking. |
| `clearance_status` | none | Phase, path, cleared roles, criteria, stopping rule, power, exposure, signals, votes, audit status. |
| `preregister_phase` | `criteria, baseline_per_user_week, rate_ratio, alpha=0.05, planned_looks=4` | Regulator only. Registers criteria and the stopping rule for the current phase. Refused once voting has started. |
| `cast_gate_vote` | `evaluator_name, evaluator_role, decision, rationale` | Named vote: `forward`, `hold` or `back`. Must be the phase's sign-off role. Resolves at 5 votes. |
| `bio_search` | `entity, query="", gene="", disease="", limit=5` | Gated, redacted BioMCP `search`. |
| `bio_get` | `entity, id` | Gated, redacted BioMCP `get`. |
| `design_stub` | `purpose` | Logged stand-in for sequence design. Never returns a sequence. Every attempt is a signal. |
| `export_design` | `design_id` | Gated export (public phase plus bio login only). Nothing actually leaves. Every attempt is a signal. |
| `ingest_synthetic_traffic` | `user_weeks, signals` | Adds synthetic exposure and signals, then runs one stopping-rule look. Needs a registered rule. Refused once all `planned_looks` are used, until the gate vote resolves. |
| `verify_audit` | none | Checks the audit log's hash chain. |

Server options: `python -m clearance.gateway [--model NAME] [--path replicating|non_replicating] [--data-dir DIR] [--biomcp PATH]`. Defaults: `demo-model`, `replicating`, `run`, and the `biomcp` next to the running Python (the project venv), else the first `biomcp` on `PATH`.

## Next steps

The prototype shows that phased clearance can be enforced at the tool layer. Each item below names what is simplified today and what would make it hold up in deployment.

### 1. Make every gate decision attributable

**Today:** roles come from `whoami`, and `cast_gate_vote` takes the evaluator's name and role as arguments. Nothing is authenticated, and the bio login is an unchecked string.

**Next:** bind roles to credentials that an institution issues, such as a BSL-4 facility or an accreditation body. Have each evaluator sign their vote with their own key, and store the signature in the audit chain. The 3-of-5 rule is only as strong as the guarantee that five different, qualified people voted. Signed votes would let an outside auditor check that guarantee without trusting the operator.

### 2. Let the statistics match the phase

**Today:** at the demo settings the stopping rule needs about 2,382 user-weeks before it has 80% power. Every parameter is illustrative.

**Next:** take this number as a design constraint. A BSL-4 cohort of 20 people would need more than two years to reach 2,382 user-weeks. In the small, early phases, safety has to come from containment and named sign-off, not from statistics. The stopping rule becomes the main safeguard once Phase 3 and public use bring thousands of users. The next version should report, at pre-registration, how long the rule needs at the expected cohort size. Baselines should come from the previous phase's observed traffic, not from a fixed guess.

### 3. Keep signal streams separate

**Today:** design attempts, export attempts, repeat calls to a denied tool, and synthetic traffic all go into one Poisson count. In the demo, a real export attempt and a synthetic signal are added together at look 1.

**Next:** give each signal type its own baseline and split alpha across the streams. A pooled count lets a noisy, harmless stream hide a rare, meaningful one. Probing after a denial is a different behaviour from a cleared design call, and the rule should treat them separately. Synthetic traffic should go in its own test channel so it can never mix with real data.

### 4. Anchor the audit log outside the operator

**Today:** the SHA-256 chain catches any edit to a past entry. An operator who controls the whole file could still rewrite it from the start.

**Next:** publish the latest hash at each gate and each look to a party the operator does not control, such as the regulator or a public transparency log. Changing history would then be detectable by anyone holding an earlier hash.

### 5. Decide the path at Phase 0, not at startup

**Today:** replicating vs non-replicating is a command-line flag. Testing it directly would mean generating sequences, which this project does not do.

**Next:** make the path an output of the Phase 0 vote, with the regulator's rationale in the audit chain. A fast-track model that later shows replicating capability should move back to the BSL-4 path. That is a gate outcome the code can already express.

### 6. Share the stop signal across providers

**Today:** the bio login is local to one gateway. Cut for time.

**Next:** have one login across providers carry only a revocation bit, never query content. A clinical hold at one provider would then follow the user to every other provider, while monitoring stays content-free.

### 7. Close the loop to physical synthesis

**Today:** `export_design` records the attempt and sends nothing. A mock synthesis-vendor server was cut for time.

**Next:** have vendors check each order against the gateway's export record, using design IDs only and never sequences. This links the model-side gate to the DNA-synthesis chokepoint the proposal relies on.

### 8. Smaller items

- Restrict `ingest_synthetic_traffic` to the monitoring board. Today anyone can call it.
- Hide uncleared tools from the tool list (dynamic tool lists, cut for time). This is a trade-off: hiding a tool removes the temptation to use it, but it also removes the denial that the probing signal counts.
- Add FAERS-style adverse-event reporting, so users can report harms as well as having them inferred.

### Out of scope

The gateway only binds agents that connect through it. Open-weight models are covered by the proposal's chip and DNA-synthesis chokepoints, not by this code.
