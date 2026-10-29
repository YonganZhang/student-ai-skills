"""Tiny real PyTorch consumer used to test the runner, not a project substitute."""
import argparse
import importlib.util
import io
from pathlib import Path

import torch
from torch import nn


class Model(nn.Module):
    def __init__(self, bug="none"):
        super().__init__()
        self.base = nn.Linear(4, 4, bias=False)
        self.branch = nn.Linear(4, 4, bias=False)
        self.scale = nn.Parameter(torch.zeros(()))
        self.bug = bug

    def forward(self, x, mask, enabled=True):
        if self.bug == "mask":
            mask = torch.ones_like(mask)
        pooled = (x * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        out = self.base(pooled)
        if enabled:
            out = out + self.scale * self.branch(pooled)
        return out.unsqueeze(-1) if self.bug == "shape" else out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("check")
    parser.add_argument("--bug", default="none")
    args = parser.parse_args()
    torch.manual_seed(7)
    torch.set_num_threads(1)
    model = Model(args.bug)
    x = torch.arange(24, dtype=torch.float32).reshape(2, 3, 4) / 24
    mask = torch.tensor([[1., 1., 0.], [1., 0., 0.]])
    if args.check == "interface":
        for batch, length in ((2, 3), (1, 5)):
            sample = torch.ones(batch, length, 4)
            out = model(sample, torch.ones(batch, length))
            assert out.shape == (batch, 4), f"axis contract violated: {out.shape}"
            assert out.dtype == sample.dtype and torch.isfinite(out).all()
    elif args.check == "training_path":
        optimizer = torch.optim.SGD(model.base.parameters() if args.bug == "optimizer" else model.parameters(), lr=0.1)
        optimizer_ids = {id(p) for group in optimizer.param_groups for p in group["params"]}
        assert all(id(p) in optimizer_ids for p in model.parameters()), "optimizer omitted parameters"
        names = {"scale", "branch.weight"}
        # inline stand-in for the unshipped mlgain probe_hooks.snapshot_params (validates names, clones values)
        params = dict(model.named_parameters())
        assert names <= params.keys(), f"unknown parameter names: {sorted(names - params.keys())}"
        before = {name: params[name].detach().clone() for name in names}
        for _ in range(4):
            optimizer.zero_grad()
            loss = (model(x, mask) - 1).square().mean()
            assert torch.isfinite(loss), "nonfinite loss"
            loss.backward()
            assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
            optimizer.step()
        # Check the real parameters, not a predicted SGD update or non-None grad.
        for name, p in model.named_parameters():
            if name in names:
                assert not torch.equal(before[name], p.detach()), f"no update: {name}"
    elif args.check == "data_semantics":
        changed = x.clone()
        changed[mask == 0] = 1000
        torch.testing.assert_close(model(x, mask), model(changed, mask), msg="masked values affected output")
        assert torch.equal(model(x, torch.zeros_like(mask)), torch.zeros(2, 4))
        # Known token identity: the second sample has only its first time point visible.
        torch.testing.assert_close(model(x, mask)[1], model.base(x[1, 0]))
    elif args.check == "baseline_control":
        pooled = (x * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True)
        torch.testing.assert_close(model(x, mask, enabled=False), model.base(pooled))
        torch.testing.assert_close(model(x, mask), model(x, mask, enabled=False))
    elif args.check == "checkpoint":
        with torch.no_grad():
            model.scale.fill_(0.3)
        data = io.BytesIO()
        torch.save(model.state_dict(), data)
        data.seek(0)
        restored = Model()
        restored.load_state_dict(torch.load(data, weights_only=True))
        torch.testing.assert_close(model(x, mask), restored(x, mask))
    else:
        raise ValueError(args.check)
    print(f"{args.check}: assertions passed")


if __name__ == "__main__":
    main()
