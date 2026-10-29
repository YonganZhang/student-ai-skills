"""wait_until_status · 通用:轮询 backend 直到显式 terminal status

设计要点(综合 v11-v13 三次失败教训):
- 不靠固定 timeout 退出 · 靠 terminal status 集合
- 超 max_seconds 仍非 terminal → raise WaitTimeout(含最后状态 + 历史)
- on_progress callback 让脚本打印进度
- 偶发 JSON 解析失败 / 网络错误不致命 · 视为 transient,记入历史
"""
from __future__ import annotations
import time
import requests
from typing import Callable, Iterable

__version__ = "1.0.0"


class WaitTimeout(Exception):
    def __init__(self, last_status: str | None, history: list, max_seconds: int):
        self.last_status = last_status
        self.history = history
        self.max_seconds = max_seconds
        super().__init__(
            f"wait_until_status: {max_seconds}s 仍未达 terminal status · "
            f"last={last_status} · history_len={len(history)}"
        )


def wait_until_status(
    poll_url: str,
    extract_status: Callable[[dict], str | None],
    terminal: Iterable[str] = ("done", "failed", "cancelled"),
    max_seconds: int = 600,
    poll_interval: float = 5,
    cookies: dict | None = None,
    headers: dict | None = None,
    request_timeout: float = 15,
    on_progress: Callable[[int, str | None, dict], None] | None = None,
) -> dict:
    """轮询 poll_url 直到 extract_status(response) 返回 terminal 集合之一。

    返回最后一次成功 GET 的 json dict(含 terminal status)。
    """
    terminal = set(terminal)
    t0 = time.time()
    history: list[tuple[int, str | None]] = []
    last_data: dict = {}
    last_status: str | None = None
    while time.time() - t0 < max_seconds:
        try:
            r = requests.get(poll_url, cookies=cookies, headers=headers,
                             timeout=request_timeout)
            data = r.json()
            status = extract_status(data)
            last_data = data
            last_status = status
            elapsed = int(time.time() - t0)
            history.append((elapsed, status))
            if on_progress:
                on_progress(elapsed, status, data)
            if status in terminal:
                return data
        except Exception as e:
            elapsed = int(time.time() - t0)
            history.append((elapsed, f"_err:{type(e).__name__}"))
            if on_progress:
                on_progress(elapsed, None, {"_error": str(e)[:120]})
        time.sleep(poll_interval)
    raise WaitTimeout(last_status, history, max_seconds)
