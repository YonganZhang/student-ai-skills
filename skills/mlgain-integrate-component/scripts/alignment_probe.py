"""Input-side checks before any model conclusion (generalised from the 1号 R13 audit, parts B and C).

Import as a library; no CLI. Needs numpy; augmentation_sync also needs scipy and overlay_png matplotlib (lazy imports).

  point_alignment(images, points, radius=1)  -> signal at labelled points minus image mean, the same with row/col swapped
                                                (negative control of the check itself) and the ratio; for point labels
  mask_alignment(images, masks)              -> mean intensity inside vs outside, the same with masks flipped
  augmentation_sync(augment, n=40, ...)      -> push synthetic images with known Gaussian spots through the caller's
                                                augmentation (image, points) -> (image, points); distance from each
                                                transformed point to the nearest bright maximum (median, p95)
  overlay_png(images, points, path)          -> grid of crops with labels drawn (look at it)
Conventions: points are (row, col) in pixels of the image they belong to. Pass whatever the real dataloader yields
(after augmentation and cropping). A swapped-axis ratio near 1 means the check cannot see the labels (bad check or bad
labels); a positive signal with a near-zero swapped control is the expected result for bright targets.
"""
from __future__ import annotations

import numpy as np


def _sample(img, pts, radius):
    h, w = img.shape[:2]
    rc = np.clip(np.round(np.asarray(pts, float)).astype(int), 0, [h - 1, w - 1])
    if radius <= 0:
        return img[rc[:, 0], rc[:, 1]]
    vals = []
    for r, c in rc:
        vals.append(img[max(0, r - radius):r + radius + 1, max(0, c - radius):c + radius + 1].max())
    return np.asarray(vals)


def point_alignment(images, points, radius: int = 1) -> dict:
    sig, swp = [], []
    for img, pts in zip(images, points):
        pts = np.asarray(pts, float).reshape(-1, 2)
        if not len(pts):
            continue
        img = np.asarray(img, float)
        z = (img - img.mean()) / (img.std() + 1e-12)
        sig.append(float(_sample(z, pts, radius).mean()))
        sw = pts[:, ::-1]
        ok = (sw[:, 0] < img.shape[0]) & (sw[:, 1] < img.shape[1])
        swp.append(float(_sample(z, sw[ok], radius).mean()) if ok.any() else 0.0)
    s, c = float(np.median(sig)), float(np.median(swp))
    return dict(n=len(sig), signal_at_labels=s, signal_swapped=c, positive_share=float(np.mean(np.array(sig) > 0)),
                ok=bool(s > 0 and s > 3 * abs(c)))


def mask_alignment(images, masks) -> dict:
    d, dflip = [], []
    for img, m in zip(images, masks):
        img = np.asarray(img, float); m = np.asarray(m) > 0
        if m.any() and (~m).any():
            d.append(img[m].mean() - img[~m].mean())
            mf = m[::-1, ::-1]
            dflip.append(img[mf].mean() - img[~mf].mean() if mf.any() and (~mf).any() else 0.0)
    return dict(n=len(d), inside_minus_outside=float(np.median(d)), flipped_control=float(np.median(dflip)))


def augmentation_sync(augment, n: int = 40, size: int = 256, n_spots: int = 30, sigma: float = 1.5, seed: int = 0,
                      margin: int = 3) -> dict:
    from scipy.ndimage import maximum_filter
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    dists = []
    for k in range(n):
        pts = rng.uniform(8, size - 8, size=(n_spots, 2))
        img = np.zeros((size, size), np.float32)
        for r, c in pts:
            img += np.exp(-((yy - r) ** 2 + (xx - c) ** 2) / (2 * sigma ** 2)).astype(np.float32)
        a_img, a_pts = augment(img, pts, k)
        a_img = np.asarray(a_img, float); a_pts = np.asarray(a_pts, float).reshape(-1, 2)
        h, w = a_img.shape[:2]
        a_pts = a_pts[((a_pts >= margin) & (a_pts < np.array([h - margin, w - margin]))).all(1)]
        mx = np.argwhere((a_img == maximum_filter(a_img, size=5)) & (a_img > 0.3 * a_img.max()))
        for p in a_pts:
            dists.append(float(np.min(np.linalg.norm(mx - p, axis=1))) if len(mx) else 99.0)
    med, p95 = float(np.median(dists)), float(np.percentile(dists, 95))
    return dict(points=len(dists), median_px=med, p95_px=p95, ok=bool(med < 0.5 and p95 < 1.5))


def overlay_png(images, points, path, n: int = 16):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    k = min(n, len(images)); cols = min(8, k); rows = (k + cols - 1) // cols
    fig, ax = plt.subplots(rows, cols, figsize=(3 * cols, 3 * rows), squeeze=False)
    for i in range(rows * cols):
        a = ax[i // cols, i % cols]; a.axis('off')
        if i < k:
            p = np.asarray(points[i], float).reshape(-1, 2)
            a.imshow(images[i], cmap='gray'); a.scatter(p[:, 1], p[:, 0], s=30, facecolors='none', edgecolors='lime', lw=1)
    fig.tight_layout(); fig.savefig(path, dpi=80); plt.close(fig)
    return str(path)
