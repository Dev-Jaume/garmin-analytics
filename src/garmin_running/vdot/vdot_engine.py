"""Equacions Daniels–Gilbert, Oxygen Power (1979), reproduïdes en recerca publicada.

Vegeu docs/METHODS.md. No reprodueix ni afirma equivalència amb les taules E/M/T/I/R.
"""

import math
from datetime import date

RUN_DISTANCES = [1500, 3000, 5000, 10000, 21097.5, 42195]


def vdot(distance_m: float, seconds: float):
    if not all(math.isfinite(x) for x in (distance_m, seconds)):
        raise ValueError("Dades no finites")
    if not 1500 <= distance_m <= 42195 or not 180 <= seconds <= 36000:
        raise ValueError("Rendiment fora del domini admès")
    minutes = seconds / 60
    velocity = distance_m / minutes
    cost = -4.60 + 0.182258 * velocity + 0.000104 * velocity**2
    fraction = 0.8 + 0.1894393 * math.exp(-0.012778 * minutes)
    fraction += 0.2989558 * math.exp(-0.1932605 * minutes)
    score = cost / fraction
    if not 10 <= score <= 100:
        raise ValueError("Resultat no plausible per al domini admès")
    return score


def equivalent_seconds(score, distance_m):
    if not math.isfinite(score) or not 10 <= score <= 100 or not 1500 <= distance_m <= 42195:
        raise ValueError("Entrada fora del domini")

    # Bisecció amb equació sense límit de temps de la interfície de rendiments.
    def score_at(seconds):
        minutes = seconds / 60
        v = distance_m / minutes
        return (-4.6 + 0.182258 * v + 0.000104 * v * v) / (
            0.8
            + 0.1894393 * math.exp(-0.012778 * minutes)
            + 0.2989558 * math.exp(-0.1932605 * minutes)
        )

    lo, hi = 30.0, 86400.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if score_at(mid) > score:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def current_performance(races, as_of, recent_days=90):
    candidates = [
        r
        for r in races
        if r.get("validated") and 0 <= (as_of - date.fromisoformat(r["date"])).days <= recent_days
    ]
    return max(candidates, key=lambda r: (r["date"], r["id"]), default=None)


def _velocity_at_cost(cost):
    return (-0.182258 + math.sqrt(0.182258**2 + 4 * 0.000104 * (cost + 4.6))) / (2 * 0.000104)


def training_estimates(score):
    """Derivació orientativa, no rèplica ni regressió de les taules oficials.

    E/I: intensitats publicades V.O2 aplicades al model de cost; M: marató equivalent;
    T: ritme de cursa d'una hora; R: equivalents 1500 m–milla. docs/METHODS.md.
    """
    if not math.isfinite(score) or not 10 <= score <= 100:
        raise ValueError("VDOT fora del domini")
    e = [1000 / _velocity_at_cost(score * p) * 60 for p in (0.59, 0.74)]
    i = [1000 / _velocity_at_cost(score * p) * 60 for p in (0.97, 1.0)]
    fraction = 0.8 + 0.1894393 * math.exp(-0.012778 * 60) + 0.2989558 * math.exp(-0.1932605 * 60)
    t = 1000 / _velocity_at_cost(score * fraction) * 60
    m = equivalent_seconds(score, 42195) / 42.195
    r = [equivalent_seconds(score, d) / (d / 1000) for d in (1500, 1609.344)]
    return [
        {
            "type": kind,
            "fast_s_per_km": min(values),
            "slow_s_per_km": max(values),
            "fast_kmh": 3600 / min(values),
            "slow_kmh": 3600 / max(values),
            "status": "Estimació del model; pendent de regressió oficial",
        }
        for kind, values in [("E", e), ("M", [m]), ("T", [t]), ("I", i), ("R", r)]
    ]


def interval_estimates(paces):
    result = []
    for pace in paces:
        for distance in (200, 300, 400, 600, 800, 1000, 1200):
            fast = pace["fast_s_per_km"] * distance / 1000
            slow = pace["slow_s_per_km"] * distance / 1000
            suitable = (
                (pace["type"] == "I" and 180 <= fast <= slow <= 300)
                or (pace["type"] == "R" and slow <= 120)
                or (pace["type"] == "T" and distance >= 1000)
            )
            if suitable:
                result.append(
                    {
                        "Tipus": pace["type"],
                        "Distància m": distance,
                        "Temps ràpid s": round(fast, 1),
                        "Temps lent s": round(slow, 1),
                    }
                )
    return result
