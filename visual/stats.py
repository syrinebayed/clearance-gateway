"""Rare-event arithmetic behind "why watch proxy signals". Pure functions, stdlib only."""
import math

CONFIDENCE = 0.95
TRIAL_SIZE = 3000  # a large pre-approval study: enough to see a 1-in-1,000 event (rule of three)
RATES = (1e-3, 1e-4, 1e-5, 1e-6)
DETECTIONS = (1.0, 0.5, 0.06)


def users_to_see_one(rate: float, detection: float = 1.0, confidence: float = CONFIDENCE) -> int:
    """Users to watch for a `confidence` chance that at least one case is detected."""
    return math.ceil(math.log(1 - confidence) / math.log(1 - rate * detection))


def chance_to_see_one(users: int, rate: float, detection: float = 1.0) -> float:
    """Probability that watching `users` people reveals at least one case."""
    return 1 - (1 - rate * detection) ** users


def rare_event_view(rate: float, detection: float) -> dict:
    """Everything the dot field needs for one (rate, detection) setting."""
    if not (1e-7 <= rate <= 0.1 and 0.01 <= detection <= 1.0):
        raise ValueError("rate must be within 1e-7..0.1 and detection within 0.01..1")
    needed = users_to_see_one(rate, detection)
    return {
        "rate": rate,
        "one_in": round(1 / rate),
        "detection": detection,
        "confidence": CONFIDENCE,
        "users_needed": needed,
        "trial_size": TRIAL_SIZE,
        "trial_share": min(1.0, TRIAL_SIZE / needed),
        "trial_chance": chance_to_see_one(TRIAL_SIZE, rate, detection),
        "cases_expected": needed * rate,
        "cases_detected": needed * rate * detection,
        "rates": list(RATES),
        "detections": list(DETECTIONS),
    }
