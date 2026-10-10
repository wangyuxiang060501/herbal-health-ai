# -*- coding: utf-8 -*-
"""结构化日志"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """极简 JSON 日志格式，便于后续接入采集（llm.call / safety.hit 等事件）"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


@contextmanager
def trace_context(trace_id: str | None = None) -> Iterator[str]:
    """生成一个 trace_id 用于贯穿一次 LLM 调用 / 一次问诊"""
    tid = trace_id or uuid.uuid4().hex[:16]
    yield tid


def timer_ms() -> int:
    return int(time.time() * 1000)
