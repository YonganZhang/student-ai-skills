"""Small reference models. Replace them with your own nn.Module; the loop stays."""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class MLP(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 64, output_dim: int = 1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(input_dim, hidden),
            nn.SiLU(),
            nn.Linear(hidden, hidden),
            nn.SiLU(),
            nn.Linear(hidden, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        groups = min(8, out_channels)
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.GroupNorm(groups, out_channels),
            nn.SiLU(),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.GroupNorm(groups, out_channels),
            nn.SiLU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class SmallUNet(nn.Module):
    """2-level U-Net for dense prediction prototypes. Input H,W must be divisible by 4."""

    def __init__(
        self,
        in_channels: int = 1,
        out_channels: int = 1,
        base: int = 8,
        return_features: bool = False,
    ):
        super().__init__()
        self.return_features = return_features
        self.down1 = ConvBlock(in_channels, base)
        self.down2 = ConvBlock(base, base * 2)
        self.bottleneck = ConvBlock(base * 2, base * 4)
        self.up1 = nn.ConvTranspose2d(base * 4, base * 2, kernel_size=2, stride=2)
        self.dec1 = ConvBlock(base * 4, base * 2)
        self.up2 = nn.ConvTranspose2d(base * 2, base, kernel_size=2, stride=2)
        self.dec2 = ConvBlock(base * 2, base)
        self.head = None if return_features else nn.Conv2d(base, out_channels, kernel_size=1)

    def forward_features(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 4:
            raise ValueError(f"SmallUNet expects (B,C,H,W), got {tuple(x.shape)}")
        h, w = x.shape[-2:]
        if h % 4 or w % 4:
            raise ValueError(f"SmallUNet H,W must be divisible by 4, got {(h, w)}")
        d1 = self.down1(x)
        d2 = self.down2(F.max_pool2d(d1, 2))
        b = self.bottleneck(F.max_pool2d(d2, 2))
        u1 = self.up1(b)
        u1 = self.dec1(torch.cat([u1, d2], dim=1))
        u2 = self.up2(u1)
        u2 = self.dec2(torch.cat([u2, d1], dim=1))
        return u2

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.forward_features(x)
        if self.return_features:
            return features
        assert self.head is not None
        return self.head(features)


class TCN(nn.Module):
    """Dilated Conv1d for (B,T,C) inputs; returns (B,out_dim)."""

    def __init__(self, in_channels: int = 2, hidden: int = 32, out_dim: int = 1, kernel_size: int = 3):
        super().__init__()
        if hidden % 8:
            raise ValueError(f"TCN hidden must be divisible by 8, got {hidden}")
        layers: list[nn.Module] = []
        channels = in_channels
        for dilation in (1, 2, 4, 8):
            padding = dilation * (kernel_size - 1) // 2
            layers.extend(
                [
                    nn.Conv1d(channels, hidden, kernel_size, padding=padding, dilation=dilation),
                    nn.GroupNorm(min(8, hidden), hidden),
                    nn.SiLU(),
                ]
            )
            channels = hidden
        self.net = nn.Sequential(*layers)
        self.head = nn.Linear(hidden, out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3:
            raise ValueError(f"TCN expects (B,T,C), got {tuple(x.shape)}")
        y = self.net(x.transpose(1, 2))
        return self.head(y[:, :, -1])


def build_model(name: str, **kwargs: object) -> nn.Module:
    models = {"mlp": MLP, "small_unet": SmallUNet, "tcn": TCN}
    if name not in models:
        raise KeyError(f"unknown model {name!r}; choose from {sorted(models)}")
    return models[name](**kwargs)

class MultiTaskModel(nn.Module):
    """Shared backbone plus one independent head per task."""

    def __init__(self, backbone: nn.Module, heads: dict[str, nn.Module]):
        super().__init__()
        if not heads:
            raise ValueError("multi-task model needs at least one head")
        self.backbone = backbone
        self.heads = nn.ModuleDict(heads)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        features = self.backbone(x)
        return {task: head(features) for task, head in self.heads.items()}


def build_head(spec: dict) -> nn.Module:
    kind = spec.get("type", "linear")
    kwargs = dict(spec.get("kwargs", {}))
    if kind == "linear":
        return nn.Linear(**kwargs)
    if kind == "conv2d":
        return nn.Conv2d(**kwargs)
    raise KeyError(f"unknown head type {kind!r}; choose from ['linear', 'conv2d']")


def build_multitask_model(backbone_cfg: dict, heads_cfg: dict) -> MultiTaskModel:
    if not isinstance(backbone_cfg, dict) or "name" not in backbone_cfg:
        raise ValueError("multi-task model needs backbone: {name, kwargs}")
    backbone = build_model(backbone_cfg["name"], **dict(backbone_cfg.get("kwargs", {})))
    heads = {task: build_head(spec) for task, spec in heads_cfg.items()}
    return MultiTaskModel(backbone, heads)
