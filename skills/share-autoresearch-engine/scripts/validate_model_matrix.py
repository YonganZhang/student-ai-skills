#!/usr/bin/env python3
"""Validate a project model-matrix plan without starting experiments."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


EVIDENCE_TIERS = {
    "confirmed_rank",
    "screen_rank",
    "effect_only",
    "contract_smoke",
    "not_rankable",
    "blocked",
}
RANKABLE_TIERS = {"confirmed_rank", "screen_rank"}
MATRIX_STAGES = {"family_screen", "champion_confirmation", "evidence_rebuild", "adjacent_innovation"}
EXECUTION_STATES = {"planned", "ready", "blocked", "completed"}
CANDIDATE_STATES = {"ready", "queued", "blocked", "completed", "rejected"}
READINESS_STATES = {"screen_ready", "confirmation_required", "evidence_rebuild_required", "blocked"}
PLACEHOLDER_MARKERS = ("REPLACE_WITH", "TODO", "TBD")


class MatrixError(ValueError):
    pass


def _require(obj: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    missing = [key for key in keys if key not in obj]
    if missing:
        raise MatrixError(f"{where}: missing fields {missing}")


def _finite_json(value: Any, where: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise MatrixError(f"{where}: NaN/Inf is forbidden")
    if isinstance(value, str) and any(marker in value.upper() for marker in PLACEHOLDER_MARKERS):
        raise MatrixError(f"{where}: unresolved placeholder {value!r}")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_json(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite_json(item, f"{where}[{index}]")


def _unique(values: list[str], where: str) -> None:
    if len(values) != len(set(values)):
        raise MatrixError(f"{where}: duplicate identifiers")


def validate_matrix(data: dict[str, Any]) -> dict[str, int]:
    _finite_json(data)
    _require(data, ("schema_version", "matrix_id", "objective", "cross_track_reporting", "tracks"), "root")
    if data["schema_version"] != "dl-model-matrix/v1":
        raise MatrixError("root: unsupported schema_version")
    reporting = data["cross_track_reporting"]
    if reporting.get("raw_score_global_ranking") is not False:
        raise MatrixError("cross_track_reporting: raw-score global ranking must be false")
    tracks = data["tracks"]
    if not isinstance(tracks, list) or not tracks:
        raise MatrixError("root: tracks must be a non-empty list")
    _unique([track.get("track_id") for track in tracks], "tracks")

    lane_count = historical_count = planned_count = rankable_count = 0
    for track in tracks:
        _require(track, ("track_id", "task_type", "current_incumbent_id", "readiness", "lanes"), f"track {track.get('track_id')}")
        if track["readiness"] not in READINESS_STATES:
            raise MatrixError(f"track {track['track_id']}: invalid readiness")
        if not track["lanes"]:
            raise MatrixError(f"track {track['track_id']}: at least one lane is required")
        _unique([lane.get("lane_id") for lane in track["lanes"]], f"track {track['track_id']} lanes")
        for lane in track["lanes"]:
            lane_count += 1
            where = f"lane {track['track_id']}/{lane.get('lane_id')}"
            _require(
                lane,
                ("lane_id", "matrix_stage", "execution_status", "primary_metric", "split", "budget_profile", "incumbent_model_id", "historical_candidates", "planned_candidates", "next_action"),
                where,
            )
            if lane["matrix_stage"] not in MATRIX_STAGES or lane["execution_status"] not in EXECUTION_STATES:
                raise MatrixError(f"{where}: invalid stage or execution_status")
            if lane["primary_metric"].get("direction") not in {"higher_is_better", "lower_is_better"}:
                raise MatrixError(f"{where}: invalid metric direction")
            split = lane["split"]
            if isinstance(split.get("count"), bool) or not isinstance(split.get("count"), int) or split["count"] < 1:
                raise MatrixError(f"{where}: split.count must be a positive integer")

            historical_ids: list[str] = []
            for candidate in lane["historical_candidates"]:
                _require(candidate, ("model_id", "family", "evidence_tier", "status", "evidence_path"), where + " historical candidate")
                historical_ids.append(candidate["model_id"])
                tier = candidate["evidence_tier"]
                if tier not in EVIDENCE_TIERS:
                    raise MatrixError(f"{where}: invalid evidence_tier {tier}")
                result = candidate.get("result")
                if result and "rank" in result and tier not in RANKABLE_TIERS:
                    raise MatrixError(f"{where}: only ranked evidence tiers may carry rank")
                if tier in {"blocked", "contract_smoke"} and result:
                    raise MatrixError(f"{where}: blocked/smoke candidate cannot carry performance result")
                historical_count += 1
                rankable_count += int(tier in RANKABLE_TIERS)
            _unique(historical_ids, where + " historical candidates")

            planned_ids: list[str] = []
            families: set[str] = set()
            for candidate in lane["planned_candidates"]:
                _require(candidate, ("model_id", "family", "role", "status", "source", "rationale"), where + " planned candidate")
                if candidate["status"] not in CANDIDATE_STATES:
                    raise MatrixError(f"{where}: invalid planned candidate status")
                planned_ids.append(candidate["model_id"])
                families.add(candidate["family"])
                planned_count += 1
            _unique(planned_ids, where + " planned candidates")
            if lane["matrix_stage"] == "family_screen" and len(families) < 3:
                raise MatrixError(f"{where}: family_screen requires at least three distinct families")
            if lane["matrix_stage"] == "champion_confirmation" and lane["incumbent_model_id"] not in planned_ids:
                raise MatrixError(f"{where}: champion_confirmation must include the incumbent")

    return {"tracks": len(tracks), "lanes": lane_count, "historical_candidates": historical_count, "rankable_candidates": rankable_count, "planned_candidates": planned_count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.matrix.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(MatrixError(f"invalid JSON constant {value}")))
        summary = validate_matrix(data)
    except (OSError, json.JSONDecodeError, MatrixError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "PASS", "matrix": str(args.matrix), "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
