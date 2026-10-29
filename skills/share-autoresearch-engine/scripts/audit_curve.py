#!/usr/bin/env python3
"""Classify a validation curve; fail closed on unreadable evidence.

Usage: python scripts/audit_curve.py <budget_guard.json>
Exit 0 = curve has a readable shape (turned up / plateau),
2 = blocked (best at cap, insufficient, still decreasing, unknown, invalid),
1 = usage/parse error.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def classify(history: list[dict], best_at_cap: bool) -> str:
    """Classify a validation curve. Lower is better; UNKNOWN means not proven."""
    if len(history) < 3:
        return "INSUFFICIENT"
    steps: list[float] = []
    losses: list[float] = []
    for row in history:
        try:
            step = float(row["step"])
            loss = float(row["val_loss"])
        except (KeyError, TypeError, ValueError):
            return "INVALID"
        if not math.isfinite(step) or not math.isfinite(loss):
            return "INVALID"
        steps.append(step)
        losses.append(loss)
    if any(later < earlier for earlier, later in zip(steps, steps[1:])):
        return "INVALID"
    best_loss = min(losses)
    last = losses[-1]
    if best_at_cap:
        return "BEST_AT_CAP"
    scale = max(abs(best_loss), 1e-6)
    tol = scale * 0.01
    tail = losses[-3:]
    if last > best_loss + tol:
        return "TURNED_UP"
    if max(tail) - min(tail) <= tol:
        return "PLATEAU"
    if tail[0] - last > tol and last < losses[0]:
        return "STILL_DECREASING"
    return "UNKNOWN"



def main() -> int:
    if len(sys.argv) != 2:
        print("usage: audit_curve.py <budget_guard.json>", file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "best_at_cap" not in payload:
        print("BLOCKED: missing best_at_cap", file=sys.stderr)
        return 2
    history = payload.get("history", [])
    max_steps = int(payload.get("max_steps", -1))
    if max_steps <= 0:
        print("BLOCKED: max_steps <= 0", file=sys.stderr)
        return 2
    best_step = int(payload.get("best_step", -1))
    best_at_cap = best_step >= max_steps
    verdict = classify(history, best_at_cap)
    print(
        json.dumps(
            {
                "verdict": verdict,
                "n_validations": len(history),
                "best_step": payload.get("best_step"),
                "best_val_loss": payload.get("best_val_loss"),
                "best_at_cap": best_at_cap,
                "last_val_loss": history[-1]["val_loss"] if history else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if verdict in {"TURNED_UP", "PLATEAU"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
