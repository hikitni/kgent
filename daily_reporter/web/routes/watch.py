# -*- coding: utf-8 -*-
"""Watch 状态与 SSE 实时日志路由（使用 watchdog 文件监听 + 定时快照调度）"""

import asyncio
import datetime as dt
import json
import logging
import threading
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from daily_reporter.snapshot import take_snapshot, should_ignore
from daily_reporter.utils import hm_to_label

from ..deps import get_config, get_config_path

router = APIRouter()
logger = logging.getLogger("daily_reporter.watch")

# ---------------------------------------------------------------------------
# Watch 状态（简单全局变量）
# ---------------------------------------------------------------------------

_watch_running = False
_stop_event = threading.Event()          # 优雅停止信号
_watch_thread: threading.Thread | None = None
_observer: Observer | None = None        # watchdog 文件监听器
_watch_log: list[dict] = []             # 最近 200 条日志
_watch_log_lock = threading.Lock()
_sse_queues: list[asyncio.Queue] = []
_sse_queues_lock = threading.Lock()

_MAX_LOG = 200


def _push_log(event: str, data: dict) -> None:
    entry = {"time": dt.datetime.now().strftime("%H:%M:%S"), "event": event, **data}
    with _watch_log_lock:
        _watch_log.append(entry)
        if len(_watch_log) > _MAX_LOG:
            _watch_log.pop(0)

    msg = f"event: {event}\ndata: {json.dumps(entry, ensure_ascii=False)}\n\n"
    with _sse_queues_lock:
        for q in list(_sse_queues):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


# _time_to_label 已迁移至 daily_reporter.utils.hm_to_label
def _time_to_label(hm: str) -> str:
    return hm_to_label(hm)


# ---------------------------------------------------------------------------
# Watchdog 文件变更处理器
# ---------------------------------------------------------------------------

class _ChangeHandler(FileSystemEventHandler):
    """检测到文件变更时推送 SSE 日志，并做节流处理。"""

    def __init__(self) -> None:
        super().__init__()
        self._recent: dict[str, float] = {}   # path -> last_event_ts
        self._throttle = 2.0                   # 同一文件 2 秒内去重

    def _should_report(self, path: str) -> bool:
        now = time.monotonic()
        last = self._recent.get(path, 0.0)
        if now - last < self._throttle:
            return False
        self._recent[path] = now
        # 防止 dict 无限膨胀
        if len(self._recent) > 5000:
            cutoff = now - self._throttle * 10
            self._recent = {k: v for k, v in self._recent.items() if v > cutoff}
        return True

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = str(event.src_path)
        try:
            cfg = get_config()
            if should_ignore(Path(src), cfg):
                return
        except Exception:
            pass
        if not self._should_report(src):
            return
        action = {
            "created": "新增", "modified": "修改",
            "deleted": "删除", "moved": "移动",
        }.get(event.event_type, event.event_type)
        _push_log("file_change", {"message": f"[{action}] {src}"})


# ---------------------------------------------------------------------------
# Watch 核心线程
# ---------------------------------------------------------------------------

def _watch_worker() -> None:
    """定时快照调度 + watchdog 文件监听。"""
    global _watch_running, _observer
    triggered_today: set = set()
    _push_log("log", {"message": "Watch 已启动"})

    # 启动 watchdog Observer
    cfg = get_config()
    handler = _ChangeHandler()
    obs = Observer()
    for wp in cfg.watch_paths:
        if wp.exists() and wp.is_dir():
            obs.schedule(handler, str(wp), recursive=True)
            _push_log("log", {"message": f"监听目录: {wp}"})
    obs.start()
    _observer = obs

    try:
        while not _stop_event.is_set():
            try:
                cfg = get_config()
                now = dt.datetime.now()
                today = now.strftime("%Y-%m-%d")
                current_hm = now.strftime("%H:%M")

                for t in cfg.auto_snapshot_times:
                    key = f"{today}-{t}"
                    if current_hm == t and key not in triggered_today:
                        label = hm_to_label(t)
                        _push_log("log", {"message": f"定时触发快照（{label}）"})
                        snap = take_snapshot(cfg, label=label, trigger="auto")
                        triggered_today.add(key)
                        _push_log("snapshot", {
                            "id": snap["id"],
                            "file_count": snap["file_count"],
                            "label": label,
                        })

                # 跨天清理
                if current_hm == "00:00":
                    triggered_today = {k for k in triggered_today if k.startswith(today)}

            except Exception as e:
                logger.warning("watch worker 异常: %s", e)
                _push_log("error", {"message": str(e)})

            # 使用 Event.wait 替代 time.sleep，可被 stop 信号立即唤醒
            _stop_event.wait(timeout=30)
    finally:
        obs.stop()
        obs.join(timeout=5)
        _observer = None
        _watch_running = False
        _push_log("log", {"message": "Watch 已停止"})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status")
async def watch_status():
    cfg = get_config()
    with _watch_log_lock:
        recent = list(_watch_log[-50:])
    return {
        "ok": True,
        "running": _watch_running,
        "auto_snapshot_times": cfg.auto_snapshot_times,
        "recent_log": recent,
    }


@router.post("/start")
async def watch_start():
    global _watch_running, _watch_thread
    if _watch_running:
        return {"ok": True, "message": "Watch 已在运行"}
    _watch_running = True
    _stop_event.clear()
    _watch_thread = threading.Thread(target=_watch_worker, daemon=True)
    _watch_thread.start()
    return {"ok": True, "message": "Watch 已启动"}


@router.post("/stop")
async def watch_stop():
    global _watch_running
    if not _watch_running:
        return {"ok": True, "message": "Watch 未在运行"}
    _stop_event.set()  # 立即唤醒 worker 线程
    return {"ok": True, "message": "Watch 停止信号已发送"}


@router.get("/stream")
async def watch_stream():
    """SSE 实时日志流"""

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    with _sse_queues_lock:
        _sse_queues.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        # 先推送一条 ping 保活
        yield "event: ping\ndata: {}\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25)
                    yield msg
                except asyncio.TimeoutError:
                    # 每 25s 发一次心跳，防止连接断开
                    yield "event: ping\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            with _sse_queues_lock:
                if queue in _sse_queues:
                    _sse_queues.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
