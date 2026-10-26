"""Consultes lleugeres i agregacions: mai carregar totes les sèries FIT a l'inici."""

from datetime import timedelta

import pandas as pd

RUNNING = {"running", "trail_running", "treadmill_running", "track_running"}


def summary_frame(rows):
    values = [
        {
            "id": r["id"],
            "Data": r["start"],
            "Esport": r["sport"],
            "km": r["metrics"]["distance_m"] / 1000
            if r["metrics"].get("distance_m") is not None
            else None,
            "Segons": r["metrics"].get("timer_s"),
            "FC mitjana": r["metrics"].get("avg_hr_bpm"),
            "Ritme s/km": r["metrics"].get("avg_pace_seconds_per_km"),
            "Flags": ", ".join(r["flags"]),
        }
        for r in rows
    ]
    frame = pd.DataFrame(
        values,
        columns=["id", "Data", "Esport", "km", "Segons", "FC mitjana", "Ritme s/km", "Flags"],
    )
    frame["Data"] = pd.to_datetime(frame["Data"], utc=True)
    return frame


def training_totals(frame):
    runs = frame[frame["Esport"].isin(RUNNING)].copy()
    runs = runs.dropna(subset=["Data"])
    # Data UTC explícita; no inferir una zona desconeguda de l'activitat.
    dates = runs["Data"].dt.tz_localize(None)
    runs["Setmana"] = dates.dt.to_period("W-SUN").dt.start_time
    runs["Mes"] = dates.dt.to_period("M").dt.start_time
    distance = runs["km"].sum() if runs["km"].notna().any() else None
    timed = runs.dropna(subset=["Segons"])
    eligible = timed[(timed["km"] > 0) & (timed["Segons"] > 0)]
    timed_km = eligible["km"].sum()
    pace = eligible["Segons"].sum() / timed_km if timed_km > 0 else None
    return {
        "km": distance,
        "hours": timed["Segons"].sum() / 3600 if not timed.empty else None,
        "pace": pace,
        "weekly": runs.groupby("Setmana", as_index=False)["km"].sum(min_count=1),
        "monthly": runs.groupby("Mes", as_index=False)["km"].sum(min_count=1),
    }


def pace_text(seconds):
    if seconds is None or pd.isna(seconds) or seconds <= 0:
        return "—"
    total = round(seconds)
    return f"{total // 60}:{total % 60:02d} min/km"


def display_frame(frame):
    shown = frame.drop(columns="id").copy()
    shown["Ritme"] = shown["Ritme s/km"].map(pace_text)
    shown["Durada"] = shown["Segons"].map(
        lambda value: (
            str(timedelta(seconds=round(value))) if value is not None and pd.notna(value) else "—"
        )
    )
    return shown.drop(columns=["Ritme s/km", "Segons"])
