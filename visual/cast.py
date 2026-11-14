"""Fictional people and preset text for the visual demo. Every name here is invented."""

MODEL = "demo-model"
BIO_LOGIN = "BIO-0042"

# One preset identity per gateway role, used by whoami.
IDENTITIES: dict[str, dict[str, str]] = {
    "regulator": {"name": "Dr. Regulator", "label": "Regulator"},
    "bsl4_staff": {"name": "BSL-4 Tech", "label": "BSL-4 staff"},
    "bsl3_staff": {"name": "BSL-3 Scientist", "label": "BSL-3 staff"},
    "accredited": {"name": "Accredited Researcher", "label": "Accredited individual"},
    "public": {"name": "Member of the public", "label": "Public user"},
}

# Five named evaluators for each sign-off role (see policy.GATE_VOTER_ROLE).
ROSTER: dict[str, list[str]] = {
    "regulator": ["Dr. Amara Osei", "Dr. Lena Fischer", "Dr. Kenji Mori", "Dr. Priya Nair", "Dr. Tomas Vega"],
    "bsl4_staff": ["Ingrid Solberg", "Samir Haddad", "Naledi Dube", "Claire Moreau", "Yuki Tanabe"],
    "bsl3_staff": ["Marco Bellini", "Aisha Rahman", "Jonas Weber", "Mei Lin Chua", "Diego Paredes"],
    "accredited": ["Dr. Hana Kovac", "Dr. Omar Farouk", "Dr. Elise Laurent", "Dr. Ravi Menon", "Dr. Sofia Lindgren"],
}

RATIONALE: dict[str, str] = {
    "forward": "Pre-registered criteria met",
    "hold": "Wants one more review cycle",
    "back": "Not convinced the criteria were met",
}

# Plain-language pass criteria a regulator registers before each gate.
CRITERIA: dict[str, str] = {
    "0": "Benchmark results hold up on re-run; release path confirmed by the expert panel",
    "1": "Nothing produced would be unsafe at BSL-3; internet adds no untested capability",
    "2": "Logging and stop signal verified; no output needed BSL-3 handling",
    "3": "No open adverse-event reports; pre-release uplift trial attested",
}

# Demo stopping-rule settings (illustrative, not calibrated), as in demo.py.
RULE: dict[str, float] = {"baseline_per_user_week": 0.002, "rate_ratio": 3.0, "alpha": 0.05, "planned_looks": 4}

# Short labels for the five phases: (containment level, one-line description).
ZONES: dict[str, tuple[str, str]] = {
    "0": ("Certification", "Test environment, regulators only"),
    "1": ("BSL-4", "Air-gapped lab, no internet"),
    "2": ("BSL-3", "Closed container with internet"),
    "3": ("Accredited", "Vetted individuals, closed container"),
    "public": ("Public", "Everyone, bio login for novel designs"),
}
