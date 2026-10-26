"""Perfil clàssic running sol·licitat, separat de la revisió Friel 2025."""

import math
from datetime import datetime

NAMES = ["Z1", "Z2", "Z3", "Z4", "Z5a", "Z5b", "Z5c"]


def heart_rate_zones(lthr: float):
    if not math.isfinite(lthr) or not 60 <= lthr <= 230:
        raise ValueError("LTHR fora del rang admès; cal revisió")
    # Límits enters contigus. El tram publicat >106% comença al primer BPM >1.06*LTHR.
    cuts = [math.ceil(lthr * p) for p in (0.85, 0.90, 0.95, 1.00, 1.03)]
    cuts.append(math.floor(lthr * 1.06) + 1)
    lower = [0, *cuts]
    upper = [cut - 1 for cut in cuts] + [None]
    return [
        {"Zona": name, "Des de BPM": lo, "Fins a BPM": hi}
        for name, lo, hi in zip(NAMES, lower, upper, strict=True)
    ]


def zone_of(hr, zones):
    if hr is None or not isinstance(hr, (int, float)) or not math.isfinite(hr):
        return None
    rounded = math.floor(hr + 0.5)
    return next(
        (
            z["Zona"]
            for z in zones
            if rounded >= z["Des de BPM"]
            and (z["Fins a BPM"] is None or rounded <= z["Fins a BPM"])
        ),
        None,
    )


def time_in_zones(activity, lthr, max_gap=10):
    zones = heart_rate_zones(lthr)
    result = dict.fromkeys(NAMES, 0.0)
    excluded = 0.0
    events = sorted(
        (e for e in activity["events"] if e.get("timestamp") and e.get("event") == "timer"),
        key=lambda e: e["timestamp"],
    )
    samples = activity["samples"]
    for left, right in zip(samples, samples[1:], strict=False):
        if not left.get("timestamp") or not right.get("timestamp"):
            continue
        begin, end = (datetime.fromisoformat(r["timestamp"]) for r in (left, right))
        seconds = (end - begin).total_seconds()
        if seconds <= 0:
            continue
        state = "unknown"
        pause_inside = False
        for event in events:
            instant = datetime.fromisoformat(event["timestamp"])
            if instant <= begin:
                state = event.get("event_type", "unknown")
            elif instant < end:
                pause_inside = True
        zone = zone_of(left.get("heart_rate"), zones)
        flagged = left.get("quality_flags") or right.get("quality_flags")
        stopped = state.startswith("stop") or pause_inside
        if seconds > max_gap or not zone or flagged or stopped:
            excluded += seconds
        else:
            result[zone] += seconds
    return {
        "seconds": result,
        "excluded_seconds": excluded,
        "policy": "Mostra esquerra, sense extrapolar l'última; exclou buits, pauses i flags",
    }


def sensor_quality(activity):
    samples = activity["samples"]
    count = len(samples)
    valid = [s.get("heart_rate") for s in samples if s.get("heart_rate") is not None]
    implausible = sum(not 30 <= hr <= 240 for hr in valid)
    jumps = sum(abs(a - b) > 25 for a, b in zip(valid, valid[1:], strict=False))
    cadence_matches = sum(
        s.get("heart_rate") is not None
        and s.get("cadence") is not None
        and abs(s["heart_rate"] - s["cadence"]) <= 3
        for s in samples
    )
    return {
        "Mostres": count,
        "FC disponible (%)": round(100 * len(valid) / count, 1) if count else 0,
        "FC fora 30–240 BPM": implausible,
        "Salts >25 BPM entre lectures": jumps,
        "Coincidències FC/cadència (indici, no prova)": cadence_matches,
    }
