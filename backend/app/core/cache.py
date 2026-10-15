# -*- coding: utf-8 -*-
"""6.2.1 热点数据缓存 —— 进程内 TTL + LRU

**为什么不用 Redis**（这是要在论文里说明白的取舍）：

| 维度 | Redis | 进程内缓存 |
| --- | --- | --- |
| 部署复杂度 | 要多起一个服务（含 docker-compose 依赖） | 零依赖 |
| 数据规模 | 无上限 | 仅缓存聚合结果，条目数个位数 |
| 一致性 | 多实例共享，天然一致 | 单实例一致；多实例各自一份 |
| 失效 | 需主动删 key | TTL 到期 + 导入数据时显式清空 |

本系统是**单机 MVP**：药材数据是静态的（导入后不再变），
真正需要缓存的是「类别统计 / 归经统计 / 数据集概况」这类**每次打开筛选面板都要全表扫一遍**的聚合，
条目数只有几十个。为这点数据引入 Redis，收益远小于运维成本。

所以这里做进程内 TTL+LRU，并**预留接口不变**：将来要多实例部署，
只需换掉 `ttl_cache` 的实现（改成写 Redis），调用方一行不用改。
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable

_lock = threading.Lock()
_REGISTRY: list[Any] = []          # 所有被装饰的函数，便于统一清空


class _Cache:
    def __init__(self, ttl: float, maxsize: int):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with _lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None, False
            expires, value = item
            if time.monotonic() > expires:
                self._data.pop(key, None)
                self.misses += 1
                return None, False
            self._data.move_to_end(key)     # LRU：命中后移到末尾
            self.hits += 1
            return value, True

    def put(self, key, value):
        with _lock:
            self._data[key] = (time.monotonic() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self):
        with _lock:
            self._data.clear()
            self.hits = self.misses = 0

    def stats(self) -> dict:
        with _lock:
            total = self.hits + self.misses
            return {
                "size": len(self._data),
                "maxsize": self.maxsize,
                "ttl_seconds": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }


def ttl_cache(ttl: float = 300.0, maxsize: int = 128,
              ignore_types: tuple = ()) -> Callable:
    """带 TTL 与 LRU 淘汰的缓存装饰器

    `ignore_types`：不参与缓存键的类型。最容易踩的坑是**把数据库 Session 算进键里**——
    每个请求都是一个新的 Session 对象，键必然不同，命中率恒为 0，
    看起来"加了缓存"实际一次都没命中。所以调用方要把 Session 类型传进来排除掉。

    另：只应缓存**不可变的普通数据**（dict / list / 标量）。
    不要缓存 SQLAlchemy ORM 实例——会话关闭后会 DetachedInstanceError。
    """
    cache = _Cache(ttl, maxsize)

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                key_args = tuple(a for a in args if not isinstance(a, ignore_types))
                key_kwargs = tuple(
                    (k, v) for k, v in sorted(kwargs.items())
                    if not isinstance(v, ignore_types)
                )
                key = (key_args, key_kwargs)
                hash(key)                       # 不可哈希就别缓存，直接走原函数
            except TypeError:
                return fn(*args, **kwargs)
            value, ok = cache.get(key)
            if ok:
                return value
            value = fn(*args, **kwargs)
            cache.put(key, value)
            return value

        wrapper.cache = cache                   # type: ignore[attr-defined]
        wrapper.cache_clear = cache.clear       # type: ignore[attr-defined]
        wrapper.cache_stats = cache.stats       # type: ignore[attr-defined]
        _REGISTRY.append(wrapper)
        return wrapper

    return deco


def cache_clear_all() -> int:
    """导入/重置数据后调用：清空全部缓存，避免读到旧统计"""
    n = 0
    for fn in _REGISTRY:
        try:
            fn.cache_clear()
            n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def cache_stats_all() -> dict[str, dict]:
    return {getattr(fn, "__name__", str(fn)): fn.cache_stats() for fn in _REGISTRY}
