"""Strip long biological sequence strings from any text before it leaves the gateway."""
import re
from dataclasses import dataclass

PLACEHOLDER = "[REDACTED-SEQUENCE]"

# Nucleotide blocks of 10+ letters, optionally split by whitespace/digits as in FASTA or GenBank layouts.
_NUC_BLOCK = r"[ACGTUNacgtun]{10,}"
_NUCLEOTIDE = re.compile(rf"{_NUC_BLOCK}(?:[\s\d]+{_NUC_BLOCK})*")
_MIN_NUCLEOTIDES = 30
# Amino-acid runs: 50+ uppercase residue letters with no spaces (plain English never does this).
_AMINO_ACID = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]{50,}")


def _redact_long_nucleotides(match: re.Match) -> str:
    letters = sum(ch.isalpha() for ch in match.group(0))
    return PLACEHOLDER if letters >= _MIN_NUCLEOTIDES else match.group(0)


@dataclass(frozen=True)
class RedactResult:
    text: str
    n_redacted: int


def redact(text: str) -> RedactResult:
    """Replace nucleotide runs (>=30) and amino-acid runs (>=50) with a placeholder."""
    before = text.count(PLACEHOLDER)
    text = _NUCLEOTIDE.sub(_redact_long_nucleotides, text)
    text = _AMINO_ACID.sub(PLACEHOLDER, text)
    return RedactResult(text=text, n_redacted=text.count(PLACEHOLDER) - before)
