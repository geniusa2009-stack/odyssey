"""Machine-readable exports (JSON, CSV). No visualisation — data for later tools."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any

from .aggregate import OUTCOME_CLASSES, StrategySummary, summarize
from .runner import MissionMetrics
from .sweep import SweepResult

REPORT_VERSION = 1
_DICT_FIELDS = {
    "objectives",
    "alerts_raised",
    "decisions_by_type",
    "rejections_by_code",
    "overrides",
}


def mission_rows_csv(rows: Iterable[MissionMetrics]) -> str:
    """One CSV row per mission. Dict fields are flattened (``objective.<id>``) or JSON-encoded."""
    rows = list(rows)
    scalar = [f.name for f in fields(MissionMetrics) if f.name not in _DICT_FIELDS]
    objective_ids = sorted({oid for r in rows for oid in r.objectives})
    header = [
        *scalar,
        *(f"objective.{o}" for o in objective_ids),
        "alerts_raised",
        "decisions_by_type",
        "rejections_by_code",
        "overrides",
    ]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for r in rows:
        d = r.as_dict()
        writer.writerow(
            [
                *(d[k] for k in scalar),
                *(r.objectives.get(o, "") for o in objective_ids),
                *(
                    json.dumps(d[k], sort_keys=True)
                    for k in (
                        "alerts_raised",
                        "decisions_by_type",
                        "rejections_by_code",
                        "overrides",
                    )
                ),
            ]
        )
    return buf.getvalue()


def summary_rows_csv(summaries: Sequence[StrategySummary]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    objective_ids = sorted({o for s in summaries for o in s.objective_rates})
    stat_fields = sorted({k for s in summaries for k in s.stats})
    header = [
        "strategy",
        "missions",
        "success_rate",
        *OUTCOME_CLASSES,
        "battery_depletion_rate",
        "crew_incapacitation_rate",
        "rover_loss_rate",
        "distinct_final_states",
        *(f"objective.{o}" for o in objective_ids),
        *(f"{k}.{q}" for k in stat_fields for q in ("mean", "p10", "p50", "p90")),
    ]
    writer.writerow(header)
    for s in summaries:
        writer.writerow(
            [
                s.strategy,
                s.missions,
                s.success_rate,
                *(s.outcome_rates[c] for c in OUTCOME_CLASSES),
                s.battery_depletion_rate,
                s.crew_incapacitation_rate,
                s.rover_loss_rate,
                s.distinct_final_states,
                *(s.objective_rates.get(o, "") for o in objective_ids),
                *(
                    getattr(s.stats[k], q)
                    for k in stat_fields
                    for q in ("mean", "p10", "p50", "p90")
                ),
            ]
        )
    return buf.getvalue()


def sweep_json(result: SweepResult, *, include_missions: bool = True) -> dict[str, Any]:
    spec = result.spec
    return {
        "report": "odyssey.balancing.sweep",
        "version": REPORT_VERSION,
        "scenario_id": spec.scenario_id,
        "scenario_hash": result.scenario_hash,
        "strategies": list(spec.strategies),
        "seeds": [spec.seeds[0], spec.seeds[-1]],
        "seed_count": len(spec.seeds),
        "overrides": dict(spec.overrides),
        "summaries": [s.as_dict() for s in summarize(result.rows)],
        "missions": [r.as_dict() for r in result.rows] if include_missions else None,
    }


def write(path: Path, text_or_obj: str | dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text_or_obj, str):
        path.write_text(text_or_obj, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(text_or_obj, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
