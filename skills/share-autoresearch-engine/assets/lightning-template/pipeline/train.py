"""Minimal generic training entrypoint. Adapt configs, not this loop."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lightning as L
import torch
import yaml
from lightning.pytorch.callbacks import LearningRateMonitor, ModelCheckpoint
from lightning.pytorch.loggers import CSVLogger

from pipeline.callbacks import BudgetGuard, CurveAudit, ManifestCallback
from pipeline.data import ArrayDataModule
from pipeline.losses import build_loss, build_metrics
from pipeline.models import build_model, build_multitask_model
from pipeline.module import MultiTaskModule, SupervisedModule

SKILL_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from structure_gate import GateError, canonical_sha, record_binding, require_card, sha_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--data-path", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--accelerator", default=None)
    parser.add_argument("--devices", type=int, default=None)
    parser.add_argument("--resume", default=None, help="checkpoint path, or 'last'")
    parser.add_argument("--test", action="store_true", help="run test once after training")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--test-path", default=None)
    parser.add_argument("--structure-card", type=Path, default=None,
                        help="structural-judgment JSON card; required for structural changes")
    parser.add_argument("--validate-only", action="store_true",
                        help="validate the structure card and exit before any optimizer step")
    return parser.parse_args()


def resolve_resume_path(out_dir: Path, value: str) -> Path:
    """Resume is same-run only; an external checkpoint is a warm start, not a resume."""
    path = (out_dir / "checkpoints" / "last.ckpt") if value == "last" else Path(value)
    path = path.expanduser().resolve()
    expected = (out_dir / "checkpoints" / "last.ckpt").resolve()
    if not path.is_file():
        raise SystemExit(f"resume checkpoint not found: {path}")
    if path != expected:
        raise SystemExit(
            f"resume only accepts {expected}; {path} is a historical/external checkpoint. "
            "Use a new run for warm starts."
        )
    return path


def check_resume_budget(out_dir: Path, max_steps: int) -> None:
    old_budget = None
    manifest = out_dir / "manifest.yaml"
    if manifest.exists():
        old = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        old_budget = old.get("budget_max_steps")
    if old_budget is None:
        resolved = out_dir / "resolved_config.yaml"
        if not resolved.exists():
            raise SystemExit("resume has no immutable budget evidence (manifest or resolved_config.yaml)")
        old_cfg = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        old_budget = (old_cfg.get("trainer") or {}).get("max_steps")
    if old_budget is None:
        raise SystemExit("resume budget evidence has no trainer.max_steps")
    if int(old_budget) != int(max_steps):
        raise SystemExit(
            f"resume budget changed: original budget={old_budget}, this run={max_steps}. "
            "A budget change is a new run, not a resume."
        )


def validate_resume_lineage(out_dir: Path, resume_path: Path) -> None:
    """Reject moved runs and rolling back behind the on-disk selection state."""
    expected = (out_dir / "checkpoints" / "last.ckpt").resolve()
    if resume_path.resolve() != expected:
        raise SystemExit(f"resume only accepts {expected}; use a new run for other weights")
    try:
        import torch

        ckpt = torch.load(resume_path, map_location="cpu", weights_only=False)
    except Exception as exc:
        raise SystemExit(f"cannot inspect resume checkpoint {resume_path}: {exc}") from exc
    callbacks = ckpt.get("callbacks", {}) if isinstance(ckpt, dict) else {}
    checkpoint_cb = next(
        (v for k, v in callbacks.items() if str(k).startswith("ModelCheckpoint")), None
    )
    if not isinstance(checkpoint_cb, dict) or not checkpoint_cb.get("dirpath"):
        raise SystemExit("resume checkpoint has no ModelCheckpoint lineage; use a new run")
    saved_dir = Path(str(checkpoint_cb["dirpath"])).expanduser().resolve()
    if saved_dir != (out_dir / "checkpoints").resolve():
        raise SystemExit(
            f"resume checkpoint belongs to {saved_dir}, not {out_dir / 'checkpoints'}; "
            "a copied/moved run is not resumable. Use a new run."
        )
    guard_path = out_dir / "budget_guard.json"
    if not guard_path.exists():
        raise SystemExit("resume requires budget_guard.json; missing selection state is not recoverable")
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    guard_state = callbacks.get("BudgetGuard")
    if not isinstance(guard_state, dict):
        raise SystemExit("resume checkpoint has no BudgetGuard state; cannot verify selection lineage")
    if "best_step" not in guard_state or "best_loss" not in guard_state:
        raise SystemExit("resume checkpoint BudgetGuard state is incomplete")
    if "best_step" not in guard or "best_val_loss" not in guard:
        raise SystemExit("on-disk budget_guard.json is incomplete")
    if int(guard_state["best_step"]) != int(guard["best_step"]):
        raise SystemExit(
            f"resume checkpoint best_step={guard_state['best_step']} != on-disk {guard['best_step']}; "
            "refusing to roll selection back behind the current best"
        )
    if abs(float(guard_state["best_loss"]) - float(guard["best_val_loss"])) > 1e-9:
        raise SystemExit("resume checkpoint best_loss differs from on-disk selection state")
    if int(ckpt.get("global_step", -1)) < int(guard["best_step"]):
        raise SystemExit("resume checkpoint is older than the on-disk best step")


def selection_recipe(cfg: dict) -> dict:
    """Same-run selection contract: effective loss/task/label interpretation, not lr/seed."""
    module = cfg.get("module", {})
    keys = ("type", "tasks", "loss", "losses", "loss_weights", "metrics", "target_dtypes")
    return {
        "module": {k: module[k] for k in keys if k in module},
        "data_target_dtypes": (cfg.get("data") or {}).get("target_dtypes"),
    }


def check_selection_recipe(out_dir: Path, recipe: dict, *, resume: bool) -> None:
    path = out_dir / "selection_recipe.json"
    if not path.exists():
        if resume:
            raise SystemExit("resume has no selection_recipe.json; cannot verify loss/task contract")
        return
    old = json.loads(path.read_text(encoding="utf-8"))
    if old != recipe:
        raise SystemExit(f"selection recipe conflict in {path}; use a new run")


def write_selection_recipe(out_dir: Path, recipe: dict) -> None:
    path = out_dir / "selection_recipe.json"
    if path.exists():
        return
    path.write_text(json.dumps(recipe, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def preflight_output(out_dir: Path, *, resume: bool, test_read_flag: Path) -> None:
    """Refuse to touch an existing run's evidence; never overwrite resolved config."""
    if test_read_flag.exists():
        raise SystemExit(
            f"test_read.flag already exists: {test_read_flag}; the test was already read. "
            "Use a new output dir and a final-test receipt, not another training run."
        )
    if not out_dir.exists():
        return
    if not resume and (out_dir / "manifest.yaml").exists():
        raise SystemExit(
            f"output_dir already has a write-once manifest: {out_dir}; "
            "use --resume for the same run or choose a new output_dir"
        )
    if not resume and (out_dir / "resolved_config.yaml").exists():
        raise SystemExit(
            f"output_dir already has resolved_config.yaml: {out_dir}; "
            "choose a new output_dir so prior evidence is not overwritten"
        )
    if not resume:
        for name in ("structure_gate.json", "structure_card.json", "structure_baseline.json", "structure_config.yaml", "selection_recipe.json"):
            if (out_dir / name).exists():
                raise SystemExit(
                    f"output_dir already has {name}: {out_dir}; choose a new output_dir"
                )


def next_resolved_path(out_dir: Path, *, resume: bool) -> Path:
    """Use one immutable config snapshot per run segment."""
    base = out_dir / "resolved_config.yaml"
    if not resume:
        if base.exists():
            raise SystemExit(f"refusing to overwrite existing config snapshot: {base}")
        return base
    index = 1
    while True:
        path = out_dir / f"resolved_config.resume-{index}.yaml"
        if not path.exists():
            return path
        index += 1


def architecture_identity(cfg: dict) -> dict:
    """Architecture identity only: not lr/seed/budget, which are experiment protocol."""
    structure = cfg.get("structure", {})
    module = cfg.get("module", {})
    return {
        "model": cfg["model"],
        "module_type": module.get("type", "single"),
        "structure": {
            "mode": structure.get("mode"),
            "baseline_reason": structure.get("baseline_reason", ""),
        },
    }


def baseline_fingerprint(cfg: dict) -> str:
    return canonical_sha(architecture_identity(cfg))


def structural_config(cfg: dict) -> dict:
    """Hash only architecture-relevant fields, so resume flags/budget/lr/seed do not change it."""
    return architecture_identity(cfg)


def check_structure_config(out_dir: Path, payload: dict) -> None:
    path = out_dir / "structure_config.yaml"
    if not path.exists():
        return
    old = yaml.safe_load(path.read_text(encoding="utf-8"))
    if canonical_sha(old) != canonical_sha(payload):
        raise SystemExit(f"structural config conflict in {path}; use a new run directory")


def write_structure_config(out_dir: Path, payload: dict) -> None:
    path = out_dir / "structure_config.yaml"
    if path.exists():
        return
    path.write_text(yaml.safe_dump(payload, sort_keys=True, allow_unicode=True), encoding="utf-8")


def check_structure_binding(out_dir: Path, card_path: Path, result: dict) -> None:
    """Read-only conflict check; record_binding is called only after all checks pass."""
    gate = out_dir / "structure_gate.json"
    if gate.exists():
        old = json.loads(gate.read_text(encoding="utf-8"))
        for key in ("card_sha256", "config_sha256"):
            if old.get(key) != result.get(key):
                raise SystemExit(f"binding conflict in {gate}: {key} changed; use a new run directory")
    snapshot = out_dir / "structure_card.json"
    if snapshot.exists() and sha_file(snapshot) != result["card_sha256"]:
        raise SystemExit(f"card snapshot conflict in {snapshot}; use a new run directory")


def check_baseline(out_dir: Path, reason: str) -> None:
    path = out_dir / "structure_baseline.json"
    if not path.exists():
        return
    old = json.loads(path.read_text(encoding="utf-8"))
    if old.get("reason") != reason:
        raise SystemExit(f"baseline declaration conflict in {path}; use a new run directory")


def write_baseline(out_dir: Path, reason: str) -> None:
    path = out_dir / "structure_baseline.json"
    if path.exists():
        return
    payload = {"schema": "structure-baseline/v1", "reason": reason}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    if args.data_path:
        cfg["data"]["data_path"] = args.data_path
    if args.output_dir:
        cfg["output_dir"] = args.output_dir
    if args.max_steps is not None:
        cfg["trainer"]["max_steps"] = args.max_steps
    if args.accelerator:
        cfg["trainer"]["accelerator"] = args.accelerator
    if args.devices is not None:
        cfg["trainer"]["devices"] = args.devices

    trainer_cfg = dict(cfg["trainer"])
    max_steps = int(trainer_cfg.get("max_steps", -1))
    if max_steps <= 0:
        raise SystemExit("max_steps must be positive; max_epochs-only runs cannot pass the cap gate")
    seed = int(cfg.get("seed", 17))
    L.seed_everything(seed, workers=True)
    torch.set_float32_matmul_precision("high")

    out_dir = Path(cfg["output_dir"]).resolve()
    test_read_flag = out_dir / "test_read.flag"
    resume_path = resolve_resume_path(out_dir, args.resume) if args.resume else None

    # Effective values must be in the snapshot, not only in local variables.
    cfg["data"]["test_read_flag"] = str(test_read_flag)
    if args.test_path:
        cfg["data"]["test_path"] = args.test_path
    if args.allow_test:
        cfg["data"]["allow_test"] = True
    cfg["run"] = {
        "config_path": str(config_path),
        "resume": resume_path is not None,
        "resumed_from": str(resume_path) if resume_path else None,
    }

    structure_cfg = dict(cfg.get("structure", {}))
    mode = structure_cfg.get("mode", "changed")
    if mode not in {"baseline", "changed"}:
        raise SystemExit("structure.mode must be 'baseline' or 'changed'")
    if args.structure_card is not None:
        mode = "changed"
        structure_cfg["card"] = str(args.structure_card)
    structure_cfg["mode"] = mode
    cfg["structure"] = structure_cfg

    structural = structural_config(cfg)
    card_path = None
    structure_result = None
    raw_reason = structure_cfg.get("baseline_reason", "")
    baseline_reason = raw_reason.strip() if isinstance(raw_reason, str) else ""
    if mode == "baseline":
        if args.structure_card is not None:
            raise SystemExit("baseline mode cannot also pass --structure-card; declare changed")
        if not baseline_reason:
            raise SystemExit(
                "structure.mode=baseline requires a nonempty string structure.baseline_reason; "
                "otherwise declare structure.mode=changed and pass --structure-card"
            )
        declared = str(structure_cfg.get("baseline_sha256", ""))
        actual_fingerprint = baseline_fingerprint(cfg)
        if declared != actual_fingerprint:
            raise SystemExit(
                "baseline fingerprint mismatch: model/module type differs from the declared baseline. "
                "Declare structure.mode=changed and pass --structure-card; do not relabel a changed "
                "model as baseline."
            )
    else:
        card_value = args.structure_card or structure_cfg.get("card")
        if not card_value:
            raise SystemExit(
                "structural change requires --structure-card (or structure.card in config); "
                "write the six-field card before any optimizer step"
            )
        card_path = Path(card_value).expanduser()
        if not card_path.is_absolute():
            card_path = (config_path.parent / card_path).resolve()
        try:
            structure_result = require_card(
                card_path,
                structural,
                required=True,
                action="training",
                expected_budget=max_steps,
                expected_seed=seed,
            )
        except GateError as exc:
            raise SystemExit(str(exc)) from exc

    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "structure_gate_ok",
                    "mode": mode,
                    "card": str(card_path) if card_path else None,
                    "structure_config_sha256": canonical_sha(structural),
                    "baseline_reason": baseline_reason if mode == "baseline" else None,
                },
                ensure_ascii=False,
            )
        )
        return

    if cfg.get("checkpoint_monitor", "val/loss") != "val/loss" or cfg.get("checkpoint_mode", "min") != "min":
        raise SystemExit(
            "this template only supports checkpoint_monitor=val/loss and checkpoint_mode=min; "
            "per-task or custom selection needs a separately audited checkpoint protocol"
        )

    preflight_output(out_dir, resume=resume_path is not None, test_read_flag=test_read_flag)
    if resume_path is not None:
        check_resume_budget(out_dir, max_steps)
        validate_resume_lineage(out_dir, resume_path)
    check_structure_config(out_dir, structural)
    recipe = selection_recipe(cfg)
    check_selection_recipe(out_dir, recipe, resume=resume_path is not None)
    if mode == "changed":
        assert card_path is not None and structure_result is not None
        check_structure_binding(out_dir, card_path, structure_result)
    else:
        check_baseline(out_dir, baseline_reason)

    out_dir.mkdir(parents=True, exist_ok=True)
    resolved_config_path = next_resolved_path(out_dir, resume=resume_path is not None)
    resolved_config_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    write_structure_config(out_dir, structural)
    write_selection_recipe(out_dir, recipe)

    if mode == "changed":
        assert card_path is not None and structure_result is not None
        try:
            record_binding(out_dir, card_path, structure_result, sys.argv)
        except GateError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        write_baseline(out_dir, baseline_reason)

    data_cfg = dict(cfg["data"])
    dm = ArrayDataModule(**data_cfg)

    model_cfg = dict(cfg["model"])
    module_cfg = dict(cfg["module"])
    multi_task = module_cfg.get("type") == "multi_task"
    if multi_task:
        module_cfg.pop("type")
        model_name = model_cfg.pop("name")
        if model_name != "multitask":
            raise SystemExit("module.type=multi_task requires model.name=multitask")
        model_kwargs = dict(model_cfg.get("kwargs", {}))
        model = build_multitask_model(
            model_kwargs.get("backbone", {}),
            model_kwargs.get("heads", {}),
        )
        task_names = list(module_cfg.pop("tasks", [])) or sorted(module_cfg.get("losses", {}))
        if not task_names:
            raise SystemExit("multi-task module needs tasks or losses")
        loss_cfg = dict(module_cfg.pop("losses", {}))
        metrics_cfg = dict(module_cfg.pop("metrics", {}))
        if set(loss_cfg) != set(task_names):
            raise SystemExit("module.losses keys must match module.tasks")
        losses = {task: build_loss(loss_cfg[task]) for task in task_names}
        metrics = {task: build_metrics(metrics_cfg.get(task, [])) for task in task_names}
        module = MultiTaskModule(
            backbone=model.backbone,
            heads=dict(model.heads),
            losses=losses,
            metrics=metrics,
            **module_cfg,
        )
    else:
        model = build_model(model_cfg.pop("name"), **model_cfg.get("kwargs", {}))
        loss_fn = build_loss(module_cfg.pop("loss"))
        metric_names = module_cfg.pop("metrics", [])
        metrics = build_metrics(metric_names)
        module = SupervisedModule(model=model, loss_fn=loss_fn, metrics=metrics, **module_cfg)

    # One selection rule for every run: lowest weighted validation loss.
    # Multi-task per-task best checkpoints are NOT supported in this template.
    manifest_cb = ManifestCallback(
        out_dir=out_dir,
        config_path=config_path,
        data_path=Path(data_cfg["data_path"]).resolve(),
        split_seed=cfg.get("split_seed"),
        train_seed=seed,
        deployment_metric_name=cfg.get("deployment_metric_name", ""),
        resume=resume_path is not None,
        resumed_from=str(resume_path) if resume_path else None,
        resolved_config_path=resolved_config_path,
        structure_mode=mode,
    )
    callbacks = [
        # Update the selected point before ModelCheckpoint serializes callback state.
        BudgetGuard(out_dir),
        ModelCheckpoint(
            dirpath=out_dir / "checkpoints",
            filename="best",
            monitor="val/loss",
            mode="min",
            save_top_k=1,
            save_last=True,
            save_on_train_epoch_end=False,
            auto_insert_metric_name=False,
        ),
        LearningRateMonitor(logging_interval="step"),
        CurveAudit(out_dir),
        manifest_cb,
    ]
    logger = CSVLogger(save_dir=str(out_dir / "logs"), name="csv", version="")
    trainer = L.Trainer(
        callbacks=callbacks,
        logger=logger,
        max_epochs=int(trainer_cfg.pop("max_epochs", -1)),
        enable_checkpointing=True,
        num_sanity_val_steps=0,
        log_every_n_steps=1,
        **trainer_cfg,
    )
    trainer.fit(module, datamodule=dm, ckpt_path=resume_path)
    if args.test:
        if not args.allow_test:
            raise SystemExit("--test requires --allow-test; test must be a deliberate one-time read")
        trainer.test(module, datamodule=dm, ckpt_path=out_dir / "checkpoints" / "best.ckpt")
    checkpoint = out_dir / "checkpoints" / "best.ckpt"
    print(f"best_checkpoint={checkpoint}")
    print(f"manifest={out_dir / 'manifest.yaml'}")
    print(f"curve_audit={out_dir / 'curve_audit.json'}")
    if resume_path:
        print(f"resumed_from={resume_path}")


if __name__ == "__main__":
    main()
