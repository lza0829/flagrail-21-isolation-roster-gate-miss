"""Compatibility service entrypoint for the skew-isolation lift."""

from app.modules.偏差隔离升 import (  
    放量策略,
    放量策略码,
    核证,
    核证数据,
    隔离偏差,
    同步隔离,
    确保结构,
)
from app.services.放量 import 放量, 装偏差隔离夹具  

certify = 核证
isolate = 隔离偏差
release = 放量

__all__ = [
    "放量策略",
    "放量策略码",
    "核证",
    "核证数据",
    "隔离偏差",
    "同步隔离",
    "确保结构",
    "放量",
    "装偏差隔离夹具",
    "certify",
    "isolate",
    "release",
]
