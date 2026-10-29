"""doctree place: candidate nodes for a doc. Read-only; says "uncertain" when unsure.

Scoring is TF-IDF over two separate token streams — CJK character bigrams and ASCII words — so a
project in one script does not degrade the other. Stopwords extend via `place.stopwords: {cjk, ascii}`.
Thresholds (`place.min_score`, `place.min_margin`) must be calibrated on held-in docs and frozen
before they are trusted; without them every verdict is "uncertain".
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from doctree_model import Config, as_list
from doctree_scan import Doc, clean_md, excerpt, mount_topics, split_frontmatter, title_and_headings
from doctree_render import ancestry

CJK_RUN = re.compile(r"[一-鿿]+")
ASCII_WORD = re.compile(r"[a-z][a-z0-9]+")
STOP_CJK = frozenset("的是 一个 这个 我们 没有 不是 可以 如果 因为 所以 已经 就是 还是 什么 怎么 时候 以及 进行 需要 "
                     "通过 之后 之前 现在 这次 这些 那些 其他 以后".split())
STOP_ASCII = frozenset({"the", "and", "for", "with", "md", "of", "to", "in", "is", "on", "by", "a", "an", "be"})
SCHEMA = "doctree-place/v1"


def tokenize_cjk(text: str, stop: frozenset[str] = STOP_CJK) -> list[str]:
    toks: list[str] = []
    for run in CJK_RUN.findall(text):
        if len(run) == 1:
            toks.append(run)
        toks += [run[i:i + 2] for i in range(len(run) - 1) if run[i:i + 2] not in stop]
    return toks


def tokenize_ascii(text: str, stop: frozenset[str] = STOP_ASCII) -> list[str]:
    words = ASCII_WORD.findall(text.lower().replace("_", " ").replace("-", " "))
    return [w for w in words if w not in stop and not w.isdigit()]


def make_tokenizer(place_cfg: dict):
    extra = place_cfg.get("stopwords") or {}
    cjk = STOP_CJK | frozenset(as_list(extra.get("cjk") if isinstance(extra, dict) else None))
    asc = STOP_ASCII | frozenset(w.lower() for w in as_list(extra.get("ascii") if isinstance(extra, dict) else None))

    def tokenize(text: str) -> list[str]:
        low = text.lower()
        return tokenize_cjk(low, cjk) + tokenize_ascii(low, asc)

    return tokenize


def doc_profile_text(d: Doc) -> str:
    return " ".join([d.title, d.title, d.summary, Path(d.path).stem.replace("-", " ")])


def query_text(title: str, summary: str, headings: list[str], stem: str) -> str:
    return " ".join([title, title, summary, " ".join(headings), stem.replace("-", " ")])


def _tf(tokens: list[str]) -> dict[str, float]:
    c: dict[str, int] = {}
    for t in tokens:
        c[t] = c.get(t, 0) + 1
    return {t: 1.0 + math.log(v) for t, v in c.items()}


def _normalize(v: dict[str, float]) -> dict[str, float]:
    s = math.sqrt(sum(x * x for x in v.values()))
    return {k: x / s for k, x in v.items()} if s else {}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())


class Scorer:
    """Node score = alpha * sim(query, node text) + (1 - alpha) * profile similarity.
    variant knn: mean of the k most similar primary docs; centroid: one vector per node."""

    def __init__(self, cfg: Config, docs: list[Doc], variant: str = "knn", alpha: float = 0.3, k: int = 3):
        self.variant, self.alpha, self.k = variant, alpha, k
        self.tokenize = make_tokenizer(cfg.place_cfg)
        self.nodes = [n for n in cfg.order if cfg.nodes[n].place != "rule-only" and n != cfg.root_id]
        self.docs = [d for d in docs if d.topics and d.topics[0] in self.nodes]
        texts = [self.tokenize(doc_profile_text(d)) for d in self.docs]
        ntexts = {n: self.tokenize(" ".join([cfg.nodes[n].title] * 2 + [cfg.nodes[n].one_line] + cfg.nodes[n].aliases * 2))
                  for n in self.nodes}
        df: dict[str, int] = {}
        for toks in [*texts, *ntexts.values()]:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self.n_total = len(texts) + len(ntexts)
        self.idf = {t: math.log((self.n_total + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self.doc_vecs = [self.vec(t) for t in texts]
        self.node_vecs = {n: self.vec(t) for n, t in ntexts.items()}
        self.by_node: dict[str, list[int]] = {n: [] for n in self.nodes}
        for i, d in enumerate(self.docs):
            self.by_node[d.topics[0]].append(i)
        self.centroids: dict[str, dict[str, float]] = {}
        for n in self.nodes:
            acc: dict[str, float] = {}
            idxs = self.by_node[n]
            for i in idxs:
                for t, x in self.doc_vecs[i].items():
                    acc[t] = acc.get(t, 0.0) + x * (1 - alpha) / len(idxs)
            for t, x in self.node_vecs[n].items():
                acc[t] = acc.get(t, 0.0) + x * (alpha if idxs else 1.0)
            self.centroids[n] = _normalize(acc)

    def vec(self, toks: list[str]) -> dict[str, float]:
        maxidf = math.log(self.n_total + 1) + 1.0
        return _normalize({t: w * self.idf.get(t, maxidf) for t, w in _tf(toks).items()})

    def score(self, qtext: str) -> list[tuple[str, float, list[str]]]:
        q = self.vec(self.tokenize(qtext))
        out = []
        for n in self.nodes:
            prof = self.centroids[n]
            if self.variant == "centroid":
                s = _cosine(q, prof)
            else:
                sims = sorted((_cosine(q, self.doc_vecs[i]) for i in self.by_node[n]), reverse=True)[: self.k]
                node_sim = _cosine(q, self.node_vecs[n])
                s = self.alpha * node_sim + (1 - self.alpha) * (sum(sims) / len(sims)) if sims else node_sim * self.alpha
            contrib = sorted(((q[t] * prof.get(t, 0.0), t) for t in q), reverse=True)
            out.append((n, round(s, 4), [t for c, t in contrib[:5] if c > 0]))
        out.sort(key=lambda x: (-x[1], x[0]))
        return out


def calibrated(th: dict) -> bool:
    return "min_score" in th and "min_margin" in th


def verdict(ranked: list[tuple[str, float, list[str]]], th: dict) -> str:
    """confident | uncertain | new-node. Uncalibrated thresholds never claim confidence."""
    if not ranked:
        return "new-node"
    s1 = ranked[0][1]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    if s1 < float(th.get("min_score", 0.0)):
        return "new-node"
    margin = (s1 - s2) / s1 if s1 > 0 else 0.0
    if not calibrated(th) or margin < float(th.get("min_margin", 0.0)):
        return "uncertain"
    return "confident"


def read_query(cfg: Config, file: Path) -> tuple[str | None, str, str, list[str], str]:
    """(repo path or None, title, mechanical summary, headings, stem). Uses the doc's own text only."""
    text = file.read_text(encoding="utf-8", errors="replace")
    _fm, body = split_frontmatter(text)
    try:
        rel: str | None = file.resolve().relative_to(cfg.root.resolve()).as_posix()
    except ValueError:
        rel = None
    title, headings = title_and_headings(body, "")
    return rel, title, excerpt(body, cfg.summary_sections), headings, file.stem


def place(cfg: Config, docs: list[Doc], file: Path | None = None, title: str = "", summary: str = "",
          th: dict | None = None, variant: str | None = None, exclude: str | None = None) -> dict:
    rel, headings, stem = None, [], ""
    if file is not None:
        rel, ftitle, fsummary, headings, stem = read_query(cfg, file)
        title, summary = title or ftitle, summary or fsummary
    exclude = exclude or rel  # an on-tree doc must not vote for itself
    pool = [d for d in docs if d.path != exclude]
    th = cfg.place_cfg if th is None else th
    rule_hits = mount_topics(cfg, rel) if rel else []
    scorer = Scorer(cfg, pool, variant=variant or str(cfg.place_cfg.get("variant", "knn")))
    ranked = scorer.score(query_text(title, summary, headings, stem))
    v = verdict(ranked, th)
    result = {
        "schema_version": SCHEMA, "enabled": True, "file": rel or (str(file) if file else None),
        "title": clean_md(title), "summary": summary[:200], "mount_rule": rule_hits,
        "verdict": "rule" if rule_hits else v, "calibrated": calibrated(th),
        "candidates": [{"node": n, "path": " › ".join(ancestry(cfg, n)), "score": s, "why": why} for n, s, why in ranked[:3]],
        "thresholds": {k: th.get(k) for k in ("min_score", "min_margin")},
    }
    if v == "new-node" and not rule_hits:
        chain = ancestry(cfg, ranked[0][0]) if ranked else []
        near = bool(ranked) and ranked[0][1] >= float(th.get("min_score", 0)) * 0.6
        # a new topic sits beside the closest existing one (same parent); far from everything -> under the root
        result["suggest_new_node"] = {"parent": chain[-2] if near and len(chain) > 1 else cfg.root_id,
                                      "note": "no node is close enough; a new node needs maintainer review"}
    return result

