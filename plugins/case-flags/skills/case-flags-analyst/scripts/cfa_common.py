"""
Shared helpers for the case-flags-analyst scripts.

Everything here exists to make the pitfalls documented in the reference files
structurally impossible rather than something a reader has to remember:

  * require_columns()  -> the "silent zero" trap (references/field-reference.md, job-f, job-g, job-h).
                          A missing FLAGS__Business_Hours_Elapsed__c makes every BH sum
                          default to 0, which reads as a real finding. We raise instead.
  * check_variance()   -> "any run showing literally zero variance across an entire
                          population is a signal to check the field list" (job-f pitfall 1).
  * median()           -> used in ~12 places across the skill; always the median, never
                          the mean, for the robustness reasons stated in references/job-c-overload.md.
  * session_cache_dir()/write_json_private()
                       -> cached pulls hold real support data, so they go in a per-user
                          0700 directory as 0600 files rather than a predictable /tmp path.

Salesforce result shapes are accepted flexibly: a bare JSON list, {"records": [...]},
or the standard {"totalSize": N, "done": true, "records": [...]} envelope.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

# Business hours in a nominal working day. Single source; see SKILL.md "Tunable constants".
WORKDAY_HOURS = 8.0

# Minimum distinct workdays before labor_per_clear is trustworthy (SKILL.md constants).
MIN_WORKDAYS_FOR_CONFIDENCE = 10


class DataError(RuntimeError):
    """Raised when input data cannot support the requested computation."""


# ------------------------------------------------------------------------ session cache


def _user_tag() -> str:
    """A per-user directory suffix, so two accounts never share a cache path."""
    for key in ("USER", "USERNAME", "LOGNAME"):
        value = os.environ.get(key)
        if value:
            return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:32]
    return str(os.getuid()) if hasattr(os, "getuid") else "user"


def session_cache_dir(create: bool = True) -> str:
    """
    Private per-user directory for cached org pulls.

    Deliberately NOT a fixed /tmp/cfa-session. That path is predictable inside a
    world-writable directory, and os.makedirs(exist_ok=True) accepts a directory that
    already exists under another user's ownership -- so on a shared host (jump box,
    build agent) someone else could pre-create it, or symlink it, and read or redirect
    cached case data. It also resolved to c:\\tmp\\cfa-session on Windows, ignoring
    %TEMP% and littering the drive root.

    The cached files hold real support data (case numbers, owner names, timestamps),
    so the directory is created 0700 and files are written 0600 by write_json_private().
    """
    path = os.path.join(tempfile.gettempdir(), f"cfa-session-{_user_tag()}")
    if create:
        _ensure_private_dir(path)
    return path


def _ensure_private_dir(path: str) -> None:
    """Create (or adopt) a directory only if it is genuinely ours, then lock it to 0700."""
    if os.path.islink(path):
        raise DataError(
            f"{path} is a symlink. Refusing to write Salesforce data through it -- "
            "remove it and re-run."
        )
    os.makedirs(path, exist_ok=True)

    if hasattr(os, "getuid"):  # POSIX only; Windows temp dirs are already per-user.
        info = os.lstat(path)
        if info.st_uid != os.getuid():
            raise DataError(
                f"{path} exists but is owned by uid {info.st_uid}, not you. Refusing to "
                "cache Salesforce data in a directory another account controls."
            )
    try:
        os.chmod(path, 0o700)
    except OSError:
        # Windows and some network filesystems ignore POSIX modes; not fatal.
        pass


def write_json_private(path: str, payload: Any) -> None:
    """Write JSON readable only by the owner. Cached org data must not be world-readable."""
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# --------------------------------------------------------------------------- loading


def load_records(path: str) -> list[dict]:
    """Load SOQL results from a JSON file, tolerating the common envelope shapes."""
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if isinstance(payload, dict):
        for key in ("records", "result", "data", "rows"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            raise DataError(
                f"{path}: expected a list of records or an object with a 'records' key, "
                f"got keys {sorted(payload)[:8]}"
            )

    if not isinstance(payload, list):
        raise DataError(f"{path}: expected a JSON list of records, got {type(payload).__name__}")

    return [_strip_attributes(r) for r in payload if isinstance(r, dict)]


def _strip_attributes(record: dict) -> dict:
    return {k: v for k, v in record.items() if k != "attributes"}


def get(record: dict, path: str, default: Any = None) -> Any:
    """
    Fetch a field, following dotted relationship paths.

    SOQL returns FLAGS__Case__r.CaseNumber nested, but some connectors flatten it,
    so try the literal key first and then walk.
    """
    if path in record:
        return record[path]

    cursor: Any = record
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return default
        cursor = cursor[part]
    return default if cursor is None else cursor


# ------------------------------------------------------------------------- guardrails


def require_columns(records: Sequence[dict], columns: Iterable[str], context: str = "") -> None:
    """
    Fail loudly when a required field is absent from every record.

    This is the silent-zero guard. Omitting FLAGS__Business_Hours_Elapsed__c from a
    SELECT does not error in SOQL -- it just makes every sum zero, which looks like a
    finding. Catching it here converts a wrong answer into a stopped run.
    """
    if not records:
        return

    columns = list(columns)
    present: set[str] = set()
    for record in records[: min(len(records), 200)]:
        present.update(record.keys())
        for key, value in record.items():
            if isinstance(value, dict):
                present.update(f"{key}.{sub}" for sub in value)

    missing = [c for c in columns if c not in present]
    if missing:
        where = f" ({context})" if context else ""
        raise DataError(
            f"Required field(s) absent from the SOQL result{where}: {', '.join(missing)}.\n"
            "Add them to the SELECT list and re-run. Note for BH fields: omitting them does "
            "NOT error in SOQL, it silently yields zeros -- which is why this is fatal here "
            "rather than a warning. See references/field-reference.md and job-f 'Known pitfalls'."
        )


def check_variance(values: Sequence[float], label: str, min_n: int = 20) -> str | None:
    """
    Detect the 'uniform, no-variance result across an entire population' signal.

    Returns a warning string, or None when the distribution looks real.
    """
    numbers = [v for v in values if v is not None]
    if len(numbers) < min_n:
        return None
    if len(set(round(v, 9) for v in numbers)) == 1:
        return (
            f"SUSPECT: {label} is identical ({numbers[0]}) across all {len(numbers)} records. "
            "Zero variance across a whole population is the signature of a missing column or a "
            "broken walk, not a real finding (job-f pitfall 1). Verify before reporting."
        )
    return None


# ------------------------------------------------------------------------------ stats


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def numbers(records: Sequence[dict], field: str) -> list[float]:
    out = []
    for record in records:
        value = to_float(get(record, field))
        if value is not None:
            out.append(value)
    return out


def median(values: Sequence[float]) -> float | None:
    """Median, the skill's default for every 'typical' figure."""
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def mean(values: Sequence[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def percentile(values: Sequence[float], p: float) -> float | None:
    """Linear-interpolation percentile; p in 0..100."""
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * (p / 100.0)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return clean[int(pos)]
    return clean[low] + (clean[high] - clean[low]) * (pos - low)


def describe(values: Sequence[float], min_n: int | None = None) -> dict:
    """
    Full summary for any distribution in the skill.

    tail_ratio is mean/median -- Job H flags a tail at >= 1.5 (SKILL.md constants),
    and it is worth carrying everywhere because a clean median sitting on one
    catastrophic case is the most misleading read available.
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return {"n": 0, "median": None, "mean": None, "note": "no values"}

    med = median(clean)
    avg = mean(clean)
    summary = {
        "n": len(clean),
        "median": med,
        "mean": avg,
        "min": min(clean),
        "max": max(clean),
        "p25": percentile(clean, 25),
        "p75": percentile(clean, 75),
        "p90": percentile(clean, 90),
        "tail_ratio": (avg / med) if med else None,
    }
    if min_n is not None and len(clean) < min_n:
        summary["low_confidence"] = (
            f"only {len(clean)} values (threshold {min_n}) -- present as low-confidence"
        )
    return summary


# -------------------------------------------------------------------------- datetimes


def parse_dt(value: Any) -> datetime | None:
    """Parse Salesforce datetimes ('2026-08-06T13:45:00.000+0000' and friends)."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip().replace("Z", "+00:00")
    # '+0000' -> '+00:00'
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def shift(dt: datetime, offset_hours: float) -> datetime:
    """Apply a fixed UTC offset, for local-time-of-day comparisons (the 8:30 cutoff)."""
    return dt.astimezone(timezone.utc) + timedelta(hours=offset_hours)


def weekday_occurrences(start: datetime, end: datetime, weekday: int) -> int:
    """
    How many times a given weekday (Mon=0) falls in [start, end].

    The intraday forecast divides a weekday's arrival count by this; getting it wrong
    (12 vs 13 Tuesdays in 90 days) skews the forecast by ~8%.
    """
    if end < start:
        start, end = end, start
    days = (end.date() - start.date()).days + 1
    first = start.date()
    return sum(1 for i in range(days) if (first + timedelta(days=i)).weekday() == weekday)


# ------------------------------------------------------------------------------ output


def fnum(value: Any, places: int = 2) -> str:
    number = to_float(value)
    return "--" if number is None else f"{number:.{places}f}"


def emit(payload: dict, as_json: bool, renderer=None) -> None:
    """Print machine JSON or a human summary. Scripts share this so output is uniform."""
    if as_json:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    elif renderer:
        renderer(payload)
    else:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")

    for warning in payload.get("warnings", []) or []:
        print(f"\n!! {warning}", file=sys.stderr)


def table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> str:
    """Minimal markdown table so script output can be pasted straight into a reply."""
    cells = [[str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in cells:
        for i, cell in enumerate(row[: len(widths)]):
            widths[i] = max(widths[i], len(cell))

    lines = [
        "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |",
        "|" + "|".join("-" * (w + 2) for w in widths) + "|",
    ]
    for row in cells:
        lines.append(
            "| " + " | ".join(str(row[i] if i < len(row) else "").ljust(widths[i])
                              for i in range(len(widths))) + " |"
        )
    return "\n".join(lines)
