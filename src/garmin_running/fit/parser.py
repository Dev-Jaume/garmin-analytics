"""FIT amb CRC estricte; preserva tots els missatges, camps i unitats."""

import io
from datetime import date, datetime, time
from typing import Any

import fitdecode

from garmin_running.domain import ActivityData, DataError, instant

MAX_FIT_BYTES = 128 * 1024 * 1024


def scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    if isinstance(value, (tuple, list)):
        return [scalar(v) for v in value]
    return value


def parse_fit(data: bytes) -> ActivityData:
    if len(data) > MAX_FIT_BYTES:
        raise DataError("FIT massa gran")
    messages: list[dict] = []
    try:
        with fitdecode.FitReader(
            io.BytesIO(data),
            check_crc=fitdecode.CrcCheck.RAISE,
            error_handling=fitdecode.ErrorHandling.RAISE,
        ) as reader:
            for frame in reader:
                if isinstance(frame, fitdecode.FitDataMessage):
                    messages.append(
                        {
                            "name": frame.name,
                            "fields": [
                                {
                                    "name": f.name,
                                    "value": scalar(f.value),
                                    "units": f.units,
                                    "raw_value": scalar(f.raw_value),
                                }
                                for f in frame.fields
                            ],
                        }
                    )
    except (fitdecode.FitError, ValueError, TypeError, KeyError) as exc:
        raise DataError("FIT invàlid; original no interpretat") from exc
    return normalize(messages)


def normalize(messages: list[dict]) -> ActivityData:
    def values(message: dict) -> dict:
        return {f["name"]: f["value"] for f in message["fields"]}

    sessions = [values(m) for m in messages if m["name"] == "session"]
    if len(sessions) != 1:
        raise DataError("Cal una sessió FIT; multisport pendent de descomposició explícita")
    session = sessions[0]
    start = instant(session.get("start_time"))
    records = [values(m) for m in messages if m["name"] == "record"]
    flags = []
    samples = []
    seen: set[str] = set()
    previous: str | None = None
    for record in records:
        row = dict(record)
        ts = instant(row.get("timestamp"))
        row["timestamp"] = ts
        row["quality_flags"] = []
        if ts is None:
            row["quality_flags"].append("missing_timestamp")
        elif ts in seen:
            row["quality_flags"].append("duplicate_timestamp")
        if ts and previous and ts < previous:
            row["quality_flags"].append("out_of_order")
        if ts:
            seen.add(ts)
            previous = ts
        # FIT escalat: m/s, metres, segons i BPM. No substituir els camps originals.
        speed = row.get("enhanced_speed")
        if speed is None:
            speed = row.get("speed")
        row["speed_mps"] = speed
        row["pace_seconds_per_km"] = 1000 / speed if speed and speed > 0 else None
        row["altitude_m"] = row.get("enhanced_altitude")
        if row["altitude_m"] is None:
            row["altitude_m"] = row.get("altitude")
        samples.append(row)
    if not start:
        flags.append("missing_start")
    if not samples:
        flags.append("missing_records")
    file_ids = [values(m) for m in messages if m["name"] == "file_id"]
    devices = [values(m) for m in messages if m["name"] == "device_info"]
    origin = file_ids[0] if file_ids else {}
    device = str(origin.get("product") or (devices[0].get("product") if devices else "") or "")
    serial = origin.get("serial_number")
    identity = f"fit:{serial}:{start}:{session.get('sport')}" if serial and start else None
    mapping = {
        "total_distance": "distance_m",
        "total_elapsed_time": "elapsed_s",
        "total_timer_time": "timer_s",
        "total_moving_time": "moving_s",
        "avg_heart_rate": "avg_hr_bpm",
        "max_heart_rate": "max_recorded_hr_bpm",
        "avg_cadence": "avg_cadence_original",
        "total_ascent": "ascent_m",
        "total_descent": "descent_m",
        "avg_speed": "avg_speed_mps",
        "max_speed": "max_speed_mps_unvalidated",
    }
    metrics = {dest: session.get(source) for source, dest in mapping.items()}
    distance, duration = metrics["distance_m"], metrics["timer_s"]
    metrics["avg_pace_seconds_per_km"] = (
        duration * 1000 / distance if distance and duration is not None else None
    )
    metrics["pace_time_basis"] = "timer_s"
    metrics["cadence_note"] = "Unitat FIT original; no es duplica automàticament"
    return ActivityData(
        start=start,
        sport=str(session.get("sport", "unknown")),
        metrics=metrics,
        samples=samples,
        laps=[values(m) for m in messages if m["name"] == "lap"],
        events=[values(m) for m in messages if m["name"] == "event"],
        messages=messages,
        flags=flags,
        device=device or None,
        identity=identity,
    )
