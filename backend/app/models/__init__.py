# -*- coding: utf-8 -*-
"""模型注册表：import 本模块即可让 Base.metadata 收集到全部表"""
from .entities import (
    Base,
    Consultation,
    FoodMedicineWhitelist,
    Herb,
    Message,
    SafetyLog,
    UsageLog,
    User,
)

__all__ = [
    "Base", "Consultation", "FoodMedicineWhitelist", "Herb",
    "Message", "SafetyLog", "UsageLog", "User",
]
