import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """每个测试使用独立 SQLite 文件，避免共享 data/灰度轨.db。"""
    from app import db, seed

    monkeypatch.delenv("数据目录", raising=False)
    monkeypatch.delenv("FLAGEAIL_DATA_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    path = tmp_path / "test-flagrail.db"
    monkeypatch.setattr(db, "库路径", path)
    seed.初始化库()
    return path
