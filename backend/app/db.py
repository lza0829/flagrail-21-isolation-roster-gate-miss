import os
import sqlite3
from pathlib import Path

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "灰度轨.db"
_默认库路径 = Path(__file__).resolve().parent.parent / "data" / "灰度轨.db"


def 当前库路径() -> Path:
    """优先环境变量；兼容 monkeypatch 的库路径或数据目录。"""
    env_dir = os.environ.get("数据目录") or os.environ.get("FLAGEAIL_DATA_DIR") or os.environ.get("DATA_DIR")
    if env_dir:
        return Path(env_dir) / "灰度轨.db"

    patched_db = Path(库路径)
    if patched_db.is_dir():
        return patched_db / "灰度轨.db"
    if patched_db != _默认库路径:
        return patched_db

    
    return Path(数据目录) / "灰度轨.db"


def 当前夹具目录() -> Path:
    env_dir = os.environ.get("夹具目录") or os.environ.get("FLAGEAIL_FIXTURE_DIR") or os.environ.get("FIXTURE_DIR")
    return Path(env_dir) if env_dir else Path(夹具目录)


def 连接() -> sqlite3.Connection:
    path = 当前库路径()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 10000")
    return c
