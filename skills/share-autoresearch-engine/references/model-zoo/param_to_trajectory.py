#!/usr/bin/env python3
"""参数→轨迹 代理建模：10 个骨干的统一适配实现（可直接 import 复用）。

## 任务形状

    G: θ ∈ R^{d_in}  →  u ∈ R^{n_ch × n_t}      推理时**没有历史序列**

这是**参数化算子学习**，不是时序预测。代理模型、井控优化、历史拟合、
不确定性量化的前向评估都是这个形状。

## 🔴 适配声明（论文必须原样写）

本文件里的 Autoformer / DLinear / PatchTST / iTransformer / TimesNet / N-BEATS
原本都是 history → future 预测器。本任务推理时没有历史可编码，故统一适配为：

> **把历史编码器换成条件向量注入，保留各模型自己的特征机制不动。**

适配对所有模型一视同仁（含 Transformer 基线），横向比较公平；
但它们**没有跑在原生设定上**，不能假装是原版对比。

## 来源与授权

见同目录 `SOURCES.md`（论文、GitHub、commit SHA、授权）；
上游原始代码按 SOURCES.md 的 commit 自行克隆到 `upstream/`（本包不随附）；实测排名原始记录未随本包发布。

## 用法

    from param_to_trajectory import ZOO
    net = ZOO["iTransformer"](d_in=24, n_ch=22, n_t=40)
    y = net(theta)            # (B, n_ch, n_t)
"""
from __future__ import annotations


import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------- 基线
class TFBase(nn.Module):
    """现有 Transformer。条件向量广播到各时刻 + 自由学习的位置嵌入。"""

    def __init__(self, d_in, n_ch, n_t, d=128, heads=4, layers=3, ff=256):
        super().__init__()
        self.cond = nn.Linear(d_in, d)
        self.pos = nn.Parameter(torch.randn(1, n_t, d) * 0.02)
        self.tr = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d, heads, ff, batch_first=True, dropout=0.0), layers)
        self.head = nn.Linear(d, n_ch)

    def forward(self, x):
        return self.head(self.tr(self.cond(x)[:, None, :] + self.pos)).transpose(1, 2)


class SeriesDecomp(nn.Module):
    """Autoformer 的序列分解:滑动平均得趋势,残差为季节项。"""

    def __init__(self, k=13):
        super().__init__()
        self.k = k
        self.avg = nn.AvgPool1d(k, stride=1, padding=0)

    def forward(self, x):                                   # x (B, T, D)
        pad = self.k // 2
        f = x[:, :1].repeat(1, pad, 1); b = x[:, -1:].repeat(1, pad, 1)
        trend = self.avg(torch.cat([f, x, b], 1).transpose(1, 2)).transpose(1, 2)
        return x - trend, trend


class AutoCorrelation(nn.Module):
    """Autoformer 的自相关:用 FFT 算时延相关,取 top-k 时延做聚合。"""

    def __init__(self, d, heads, factor=1):
        super().__init__()
        self.h, self.dk = heads, d // heads
        self.q, self.k, self.v, self.o = (nn.Linear(d, d) for _ in range(4))
        self.factor = factor

    def forward(self, x):
        B, T, D = x.shape
        q = self.q(x).view(B, T, self.h, self.dk).permute(0, 2, 3, 1)
        k = self.k(x).view(B, T, self.h, self.dk).permute(0, 2, 3, 1)
        v = self.v(x).view(B, T, self.h, self.dk).permute(0, 2, 3, 1)
        corr = torch.fft.irfft(torch.fft.rfft(q, dim=-1) * torch.conj(torch.fft.rfft(k, dim=-1)),
                               n=T, dim=-1)                 # (B,h,dk,T) 时延相关
        top = max(1, int(self.factor * np.log(max(T, 2))))
        # 🔴 按原文 time_delay_agg_training:时延在 batch 与 head 上取均值后共享,
        #    这样可以整张量 roll。逐 (b,h) 循环在 600 epoch 下慢到不可用。
        mean_corr = corr.mean(dim=(1, 2))                   # (B,T)
        idx = torch.topk(mean_corr.mean(0), top).indices    # (top,)
        p = torch.softmax(torch.stack([mean_corr[:, i] for i in idx], -1), -1)  # (B,top)
        out = torch.zeros_like(v)
        for i in range(top):
            out = out + torch.roll(v, -int(idx[i].item()), dims=-1) * p[:, i][:, None, None, None]
        return self.o(out.permute(0, 3, 1, 2).reshape(B, T, D))


class Autoformer(nn.Module):
    """Autoformer 骨干。🔴 无历史可编码,故为 decoder-only:条件向量广播后过
    (自相关 + 序列分解) 堆叠。这是把时序预测模型搬到本任务的**最合理**改法,
    也正因为如此,它的表现能说明"架构错配"这个论断成不成立。"""

    def __init__(self, d_in, n_ch, n_t, d=128, heads=4, layers=2, ff=256, k=13):
        super().__init__()
        self.cond = nn.Linear(d_in, d)
        self.pos = nn.Parameter(torch.randn(1, n_t, d) * 0.02)
        self.ac = nn.ModuleList([AutoCorrelation(d, heads) for _ in range(layers)])
        self.dc = nn.ModuleList([SeriesDecomp(k) for _ in range(2 * layers)])
        self.ffn = nn.ModuleList([nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Linear(ff, d))
                                  for _ in range(layers)])
        self.n1 = nn.ModuleList([nn.LayerNorm(d) for _ in range(layers)])
        self.head = nn.Linear(d, n_ch)
        self.thead = nn.Linear(d, n_ch)

    def forward(self, x):
        h = self.cond(x)[:, None, :] + self.pos
        trend = 0
        for i, (ac, ffn, n1) in enumerate(zip(self.ac, self.ffn, self.n1)):
            h, t1 = self.dc[2 * i](n1(h + ac(h)))
            h, t2 = self.dc[2 * i + 1](h + ffn(h))
            trend = trend + t1 + t2
        return (self.head(h) + self.thead(trend)).transpose(1, 2)


class DeepONet(nn.Module):
    """DeepONet:branch 编码参数 θ,trunk 编码坐标 t,内积得 u(θ)(t)。
    算子学习的两大标准架构之一,天然匹配"参数 → 函数"这个任务形状。"""

    def __init__(self, d_in, n_ch, n_t, p=128, width=256, depth=4):
        super().__init__()
        def mlp(i, o):
            L = [nn.Linear(i, width), nn.GELU()]
            for _ in range(depth - 2):
                L += [nn.Linear(width, width), nn.GELU()]
            return nn.Sequential(*L, nn.Linear(width, o))
        self.branch = mlp(d_in, n_ch * p)
        self.trunk = mlp(1, p)
        self.p, self.n_ch = p, n_ch
        self.register_buffer("t", torch.linspace(0, 1, n_t)[:, None])
        self.b0 = nn.Parameter(torch.zeros(n_ch, n_t))

    def forward(self, x):
        b = self.branch(x).view(-1, self.n_ch, self.p)
        return torch.einsum("bcp,tp->bct", b, self.trunk(self.t)) + self.b0


class SpectralConv1d(nn.Module):
    """FNO 的核心:在傅里叶域对**每个模态**乘一组独立的可学习复权重。
    这正是谱偏差的对症药 —— 高频模态有自己的参数,不必与低频抢容量。"""

    def __init__(self, cin, cout, modes):
        super().__init__()
        self.modes = modes
        s = 1.0 / (cin * cout)
        self.w = nn.Parameter(s * torch.randn(cin, cout, modes, 2))

    def forward(self, x):                                   # x (B, C, T)
        T = x.shape[-1]
        xf = torch.fft.rfft(x, dim=-1)
        m = min(self.modes, xf.shape[-1])
        w = torch.view_as_complex(self.w[..., :m, :].contiguous())
        out = torch.zeros(x.shape[0], self.w.shape[1], xf.shape[-1],
                          dtype=torch.cfloat, device=x.device)
        out[..., :m] = torch.einsum("bim,iom->bom", xf[..., :m], w)
        return torch.fft.irfft(out, n=T, dim=-1)


class FNO1d(nn.Module):
    """FNO:把 θ 抬升成时间轴上的函数,再过若干谱卷积块。
    油藏代理模型文献的主流骨干(U-FNO 用于 CO₂ 封存等)。"""

    def __init__(self, d_in, n_ch, n_t, width=64, modes=16, layers=4):
        super().__init__()
        self.lift = nn.Linear(d_in + 1, width)              # +1 = 归一化时间坐标
        self.sp = nn.ModuleList([SpectralConv1d(width, width, modes) for _ in range(layers)])
        self.pw = nn.ModuleList([nn.Conv1d(width, width, 1) for _ in range(layers)])
        self.proj = nn.Sequential(nn.Linear(width, 128), nn.GELU(), nn.Linear(128, n_ch))
        self.register_buffer("t", torch.linspace(0, 1, n_t))

    def forward(self, x):
        B, T = x.shape[0], self.t.shape[0]
        g = torch.cat([x[:, None, :].expand(B, T, x.shape[1]),
                       self.t[None, :, None].expand(B, T, 1)], -1)
        h = self.lift(g).transpose(1, 2)                    # (B, W, T)
        for sp, pw in zip(self.sp, self.pw):
            h = F.gelu(sp(h) + pw(h))
        return self.proj(h.transpose(1, 2)).transpose(1, 2)


# ---------------------------------------------------------------- 我们的模型
def fourier_features(t, n_bands):
    """Tancik et al. NeurIPS 2020 的多尺度 sin/cos 基。
    原论文证明它能让网络摆脱谱偏差 —— 这正是 Gap 分析测到的病灶。"""
    f = 2.0 ** torch.arange(n_bands, device=t.device, dtype=t.dtype)   # 1,2,4,...
    a = t[:, None] * f[None, :] * 2 * np.pi
    return torch.cat([torch.sin(a), torch.cos(a)], -1)                # (T, 2*n_bands)


class OursNet(nn.Module):
    """最优骨干 + 两个针对谱偏差的模块(可逐项消融)。

    ff   : 位置嵌入换成傅里叶特征(而非自由学习的 pos)
    film : 用 θ 对每个时刻做 FiLM 调制(而非单向量相加) —— 让条件能**逐时刻**
           改变响应,是"参数 → 轨迹"这个形状更自然的注入方式
    """

    def __init__(self, d_in, n_ch, n_t, d=128, heads=4, layers=3, ff_dim=256,
                 n_bands=8, use_ff=True, use_film=True):
        super().__init__()
        self.use_ff, self.use_film = use_ff, use_film
        self.cond = nn.Linear(d_in, d)
        self.register_buffer("t", torch.linspace(0, 1, n_t))
        if use_ff:
            self.pos_proj = nn.Linear(2 * n_bands, d)
            self.n_bands = n_bands
        else:
            self.pos = nn.Parameter(torch.randn(1, n_t, d) * 0.02)
        if use_film:
            self.film = nn.Linear(d_in, 2 * d)
        self.tr = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d, heads, ff_dim, batch_first=True, dropout=0.0), layers)
        self.head = nn.Linear(d, n_ch)

    def forward(self, x):
        pos = (self.pos_proj(fourier_features(self.t, self.n_bands))[None]
               if self.use_ff else self.pos)
        h = self.cond(x)[:, None, :] + pos
        if self.use_film:
            g, b = self.film(x).chunk(2, -1)
            h = h * (1 + g[:, None, :]) + b[:, None, :]
        return self.head(self.tr(h)).transpose(1, 2)


def spectral_loss(pred, true, alpha=1.0, beta=0.5):
    """MSE + 频域按模态加权的误差。

    Gap 实测:模态 0 信噪比 15559,模态 20 只有 896(衰减 17×)。
    权重 (1+k)^beta 随模态号上升,直接补偿这个衰减。beta=0 时退化为普通频域 MSE。
    """
    mse = F.mse_loss(pred, true)
    fp, ft = torch.fft.rfft(pred, dim=-1), torch.fft.rfft(true, dim=-1)
    k = torch.arange(fp.shape[-1], device=pred.device, dtype=pred.dtype)
    w = (1.0 + k) ** beta
    sp = ((fp - ft).abs() ** 2 * w).mean() / w.mean() / pred.shape[-1]
    return mse + alpha * sp



import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class _Decomp(nn.Module):
    def __init__(self, k=13):
        super().__init__()
        self.k = k; self.avg = nn.AvgPool1d(k, stride=1)

    def forward(self, x):                                    # (B, C, T)
        p = self.k // 2
        xp = torch.cat([x[..., :1].repeat(1, 1, p), x, x[..., -1:].repeat(1, 1, p)], -1)
        tr = self.avg(xp)
        return x - tr, tr


class DLinear(nn.Module):
    """Zeng et al. AAAI 2023。机制:序列分解 + **沿时间轴**的线性层(逐通道共享)。

    适配:先用一层线性从 θ 得到初始轨迹估计,再按 DLinear 原样做分解 + 双分支时间线性。
    这样"时间轴线性层"这个核心机制被完整保留。
    """

    def __init__(self, d_in, n_ch, n_t, k=13, **_):
        super().__init__()
        self.n_ch, self.n_t = n_ch, n_t
        self.stem = nn.Linear(d_in, n_ch * n_t)
        self.dec = _Decomp(k)
        self.lin_s = nn.Linear(n_t, n_t)
        self.lin_t = nn.Linear(n_t, n_t)

    def forward(self, x):
        z = self.stem(x).view(-1, self.n_ch, self.n_t)
        s, t = self.dec(z)
        return self.lin_s(s) + self.lin_t(t)


class PatchTST(nn.Module):
    """Nie et al. ICLR 2023。机制:把时间轴切成 patch,注意力作用在 patch 之间。

    适配:没有历史可切,故用**可学习的 patch 查询** + θ 条件注入,
    再由 Transformer 在 patch 间交互,最后每个 patch 解码出 patch_len 个时刻。
    """

    def __init__(self, d_in, n_ch, n_t, d=128, heads=4, layers=3, ff=256, patch=8, **_):
        super().__init__()
        assert n_t % patch == 0, f"n_t={n_t} 必须能被 patch={patch} 整除"
        self.np, self.pl, self.n_ch = n_t // patch, patch, n_ch
        self.cond = nn.Linear(d_in, d)
        self.q = nn.Parameter(torch.randn(1, self.np, d) * 0.02)
        self.tr = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d, heads, ff, batch_first=True, dropout=0.0), layers)
        self.head = nn.Linear(d, n_ch * patch)

    def forward(self, x):
        h = self.tr(self.cond(x)[:, None, :] + self.q)       # (B, np, d)
        o = self.head(h).view(-1, self.np, self.n_ch, self.pl)
        return o.permute(0, 2, 1, 3).reshape(-1, self.n_ch, self.np * self.pl)


class ITransformer(nn.Module):
    """Liu et al. ICLR 2024。机制:**倒置** —— 每个变量(通道)整条序列当一个 token,
    注意力作用在**变量之间**,而不是时间步之间。

    本任务有 22 个通道(11 井 × 2 相),井间干扰是真实物理,跨通道注意力天然对口。
    适配:每个通道的 token = 共享的 θ 嵌入 + 该通道自己的可学习通道嵌入。
    """

    def __init__(self, d_in, n_ch, n_t, d=128, heads=4, layers=3, ff=256, **_):
        super().__init__()
        self.n_ch = n_ch
        self.cond = nn.Linear(d_in, d)
        self.ch_emb = nn.Parameter(torch.randn(1, n_ch, d) * 0.02)
        self.tr = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d, heads, ff, batch_first=True, dropout=0.0), layers)
        self.head = nn.Linear(d, n_t)

    def forward(self, x):
        h = self.cond(x)[:, None, :] + self.ch_emb           # (B, n_ch, d) —— token 是通道
        return self.head(self.tr(h))                         # (B, n_ch, n_t)


class TimesBlock(nn.Module):
    """TimesNet 核心:FFT 找 top-k 主周期 → 把 1D 序列重排成 (周期 × 周期数) 的 2D →
    用 2D Inception 卷积捕捉**周期内**与**周期间**的变化 → 按振幅加权求和。"""

    def __init__(self, d, n_t, k=3, hid=32):
        super().__init__()
        self.k, self.n_t = k, n_t
        self.conv = nn.Sequential(
            nn.Conv2d(d, hid, 3, padding=1), nn.GELU(), nn.Conv2d(hid, d, 3, padding=1))

    def forward(self, x):                                    # (B, T, d)
        B, T, D = x.shape
        amp = torch.fft.rfft(x, dim=1).abs().mean(-1)        # (B, F)
        amp[:, 0] = 0
        A = amp.mean(0)
        k = min(self.k, max(1, A.shape[0] - 1))
        top = torch.topk(A, k).indices
        outs, ws = [], []
        for f in top:
            f = int(f.item())
            per = max(1, T // max(f, 1))
            pad = (-T) % per
            xp = F.pad(x.transpose(1, 2), (0, pad)).transpose(1, 2) if pad else x
            L = xp.shape[1]
            z = xp.reshape(B, L // per, per, D).permute(0, 3, 1, 2)   # (B,d,行,周期)
            z = self.conv(z).permute(0, 2, 3, 1).reshape(B, L, D)[:, :T]
            outs.append(z); ws.append(amp[:, f])
        w = torch.softmax(torch.stack(ws, -1), -1)           # (B,k)
        return x + sum(o * w[:, i][:, None, None] for i, o in enumerate(outs))


class TimesNet(nn.Module):
    """Wu et al. ICLR 2023。适配:θ 条件广播成时间序列后过 TimesBlock 堆叠。"""

    def __init__(self, d_in, n_ch, n_t, d=128, layers=2, k=3, **_):
        super().__init__()
        self.cond = nn.Linear(d_in, d)
        self.pos = nn.Parameter(torch.randn(1, n_t, d) * 0.02)
        self.blocks = nn.ModuleList([TimesBlock(d, n_t, k) for _ in range(layers)])
        self.norms = nn.ModuleList([nn.LayerNorm(d) for _ in range(layers)])
        self.head = nn.Linear(d, n_ch)

    def forward(self, x):
        h = self.cond(x)[:, None, :] + self.pos
        for b, n in zip(self.blocks, self.norms):
            h = n(b(h))
        return self.head(h).transpose(1, 2)


class NBeats(nn.Module):
    """Oreshkin et al. ICLR 2020。机制:**基展开 + 残差堆叠** ——
    每个 block 从残差里预测一组基系数,乘上基得到一份预测,再把残差减掉,层层累加。

    🔴 本项目唯一成立的改进(傅里叶位置嵌入)就是基函数方法,而 N-BEATS 把基展开
    做成了整个架构。所以它是本批里**先验最相关**的一个。

    适配:无历史 → 无 backcast,残差在 **θ 的隐表示**上做。
    """

    def __init__(self, d_in, n_ch, n_t, width=256, depth=3, blocks=4, basis=32, **_):
        super().__init__()
        self.n_ch, self.n_t, self.nb = n_ch, n_t, blocks
        self.mlps = nn.ModuleList()
        self.coef = nn.ModuleList()
        self.back = nn.ModuleList()
        for _ in range(blocks):
            L = [nn.Linear(d_in if not self.mlps else width, width), nn.GELU()]
            for _ in range(depth - 1):
                L += [nn.Linear(width, width), nn.GELU()]
            self.mlps.append(nn.Sequential(*L))
            self.coef.append(nn.Linear(width, n_ch * basis))
            self.back.append(nn.Linear(width, d_in))
        self.basis = nn.Parameter(torch.randn(basis, n_t) * (1.0 / np.sqrt(basis)))
        self.basis_dim = basis

    def forward(self, x):
        res, out = x, 0
        for i in range(self.nb):
            h = self.mlps[i](res if i == 0 else h_prev)
            h_prev = h
            c = self.coef[i](h).view(-1, self.n_ch, self.basis_dim)
            out = out + torch.einsum("bcp,pt->bct", c, self.basis)
            res = res - self.back[i](h)
        return out




ZOO = {"Transformer": TFBase, "Autoformer": Autoformer, "DeepONet": DeepONet,
       "FNO": FNO1d, "FourierPos": OursNet, "DLinear": DLinear, "PatchTST": PatchTST,
       "iTransformer": ITransformer, "TimesNet": TimesNet, "N-BEATS": NBeats}
