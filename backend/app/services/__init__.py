# -*- coding: utf-8 -*-
"""业务服务层

刻意**不做** eager import：
编排层（app/orchestration）需要 data_loader，而 service 层反过来需要
orchestration 的 NODE_LABELS —— 若本文件在包初始化时就导入
consultation_service，会形成
    services.__init__ → consultation_service → orchestration.nodes → services.data_loader
的循环导入。保持惰性即可单向依赖。
"""
from __future__ import annotations

__all__ = ["consultation_service", "data_loader", "herb_service", "symptom_extraction"]
