# -*- coding: utf-8 -*-
"""/api/v1 路由"""
from . import router

__all__ = ["router", "api_router"]

from .router import api_router  # noqa: E402
