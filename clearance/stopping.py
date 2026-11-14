"""Pre-registered Poisson stopping rule on content-free proxy signals (stdlib only)."""
import math
from dataclasses import dataclass

_MAX_USER_WEEKS = 1e9
_SEARCH_STEP = 1.05


@dataclass(frozen=True)
class Prereg:
    phase: str
    criteria: str                  # plain-language pass/hold/back criteria
    baseline_per_user_week: float  # expected proxy-signal rate if all is well
    rate_ratio: float              # elevation the rule must detect (e.g. 3.0)
    alpha: float                   # overall false-alarm budget for the phase
    planned_looks: int             # Pocock-style: alpha / planned_looks per look
    registered_by: str

    @property
    def alpha_per_look(self) -> float:
        return self.alpha / self.planned_looks


@dataclass(frozen=True)
class RuleVerdict:
    fired: bool
    p_value: float
    alpha_per_look: float
    expected: float
    observed: int
    look: int


def poisson_sf(k: int, mu: float) -> float:
    """P(X >= k) for X ~ Poisson(mu)."""
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    cdf = sum(math.exp(i * math.log(mu) - mu - math.lgamma(i + 1)) for i in range(k))
    return max(0.0, 1.0 - cdf)


def check(prereg: Prereg, user_weeks: float, observed: int, look: int) -> RuleVerdict:
    """One-sided test of observed signals against baseline * user_weeks at this look."""
    expected = prereg.baseline_per_user_week * user_weeks
    p_value = poisson_sf(observed, expected)
    return RuleVerdict(
        fired=p_value < prereg.alpha_per_look,
        p_value=p_value,
        alpha_per_look=prereg.alpha_per_look,
        expected=expected,
        observed=observed,
        look=look,
    )


def _critical_count(expected: float, alpha_look: float) -> int:
    """Smallest count that would fire the rule when the baseline holds."""
    k = 0
    while poisson_sf(k, expected) >= alpha_look:
        k += 1
    return k


def _power(prereg: Prereg, user_weeks: float) -> float:
    expected = prereg.baseline_per_user_week * user_weeks
    k = _critical_count(expected, prereg.alpha_per_look)
    return poisson_sf(k, expected * prereg.rate_ratio)


def required_user_weeks(prereg: Prereg, power: float = 0.8) -> float:
    """Exposure needed before the rule has `power` to fire if the true rate is rate_ratio * baseline."""
    user_weeks = 1.0 / prereg.baseline_per_user_week
    while user_weeks < _MAX_USER_WEEKS:
        if _power(prereg, user_weeks) >= power:
            return round(user_weeks)
        user_weeks *= _SEARCH_STEP
    return math.inf
