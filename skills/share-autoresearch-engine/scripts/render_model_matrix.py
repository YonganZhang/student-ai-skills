#!/usr/bin/env python3
"""Render a validated model matrix as a compact Markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_model_matrix import validate_matrix


def _result_text(candidate: dict[str, Any]) -> str:
    result = candidate.get("result")
    if not result:
        return "—"
    parts = []
    handled = {"rank", "value", "note"}
    if "rank" in result:
        parts.append(f"rank={result['rank']}")
    if "value" in result:
        parts.append(f"value={result['value']:.6g}" if isinstance(result["value"], float) else f"value={result['value']}")
    for key in ("relative_primary_improvement", "relative_improvement_vs_pykrige", "delta_vs_incumbent"):
        if key in result:
            parts.append(f"{key}={result[key]:.4%}")
            handled.add(key)
    for key, value in result.items():
        if key not in handled:
            parts.append(f"{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    if "note" in result:
        parts.append(str(result["note"]))
    return "; ".join(parts) if parts else json.dumps(result, ensure_ascii=False, sort_keys=True)


def render(data: dict[str, Any], source: str) -> str:
    summary = validate_matrix(data)
    lines = [
        f"# 模型矩阵：{data['matrix_id']}",
        "",
        f"> 由 `{source}` 生成；只在同一 lane 内比较原始指标。",
        "",
        "## 总览",
        "",
        f"- 赛道：{summary['tracks']}；可比较 lane：{summary['lanes']}。",
        f"- 历史候选记录：{summary['historical_candidates']}；具 rank 资格：{summary['rankable_candidates']}。",
        f"- 下一轮计划模型/对照：{summary['planned_candidates']}。",
        "",
        "| 赛道 | 当前 incumbent | readiness | lane 数 | 历史候选 | 可排名 | 待测 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for track in data["tracks"]:
        historical = [candidate for lane in track["lanes"] for candidate in lane["historical_candidates"]]
        planned = [candidate for lane in track["lanes"] for candidate in lane["planned_candidates"]]
        rankable = sum(candidate["evidence_tier"] in {"confirmed_rank", "screen_rank"} for candidate in historical)
        lines.append(
            f"| {track['track_id']} | `{track['current_incumbent_id']}` | {track['readiness']} | {len(track['lanes'])} | {len(historical)} | {rankable} | {len(planned)} |"
        )

    for track in data["tracks"]:
        lines.extend(["", f"## {track['track_id']}", ""])
        for lane in track["lanes"]:
            lines.extend(
                [
                    f"### {lane['lane_id']}",
                    "",
                    f"阶段：`{lane['matrix_stage']}`；执行：`{lane['execution_status']}`；主指标：`{lane['primary_metric']['name']}`（{lane['primary_metric']['direction']}）。",
                    "",
                    "历史证据：",
                    "",
                    "| 模型 | 家族 | 证据等级 | 状态 | 结果 |",
                    "|---|---|---|---|---|",
                ]
            )
            for candidate in lane["historical_candidates"]:
                lines.append(
                    f"| `{candidate['model_id']}` | {candidate['family']} | {candidate['evidence_tier']} | {candidate['status']} | {_result_text(candidate)} |"
                )
            lines.extend(["", "下一轮：", "", "| 模型/对照 | 家族 | 角色 | 状态 | 理由 |", "|---|---|---|---|---|"])
            for candidate in lane["planned_candidates"]:
                lines.append(
                    f"| `{candidate['model_id']}` | {candidate['family']} | {candidate['role']} | {candidate['status']} | {candidate['rationale']} |"
                )
            lines.extend(["", f"下一动作：{lane['next_action']}。"])
    lines.extend(["", "## 跨赛道口径", "", "不对不同任务的原始 mIoU、F1、RMSE 或 MAE 做总排名。跨赛道只汇总相对 incumbent 改善、稳定通过率、实际改善达标率、失败率和 BETU。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.matrix.read_text(encoding="utf-8"))
    report = render(data, str(args.matrix))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
