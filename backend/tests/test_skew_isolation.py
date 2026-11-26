import json
import threading
from pathlib import Path

from app.modules import 偏差隔离升 as 域
from app.services import 入轨, 分桶, 下发, 回读, 放量

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def 准备票(票号: str, 键: str = "flag.skew", 版本键: str = "flag.skew@1") -> None:
    入轨.入一批({
        "版本": [{
            "开关键": 键,
            "版本号": 1,
            "版本键": 版本键,
            "载荷": {"enabled": True},
        }]
    })
    分桶.写桶({
        "桶键": f"{键}-bucket",
        "开关键": 键,
        "桶类型": "边缘组",
        "规则": {"edges": ["edge-a", "edge-b", "edge-c"]},
    })
    下发.下一票({
        "票号": 票号,
        "版本键": 版本键,
        "桶键": f"{键}-bucket",
    })


def 两确认一偏差(票号: str, 版本键: str = "flag.skew@1") -> None:
    for edge in ("edge-a", "edge-b"):
        回读.记回读({
            "票号": 票号,
            "边缘键": edge,
            "所见版本键": 版本键,
            "结果": "确认",
        })
    
    skew = 回读.记回读({
        "票号": 票号,
        "边缘键": "edge-c",
        "所见版本键": "flag.skew@0",
        "结果": "确认",
    })
    assert skew["结果"] == "偏差"


def test_两确认一偏差_核证列出三集且不吞偏差(db_path):
    ticket = "票-unit-1"
    准备票(ticket)
    两确认一偏差(ticket)

    cert = 域.核证(ticket)

    assert cert["确认集"] == ["edge-a", "edge-b"]
    assert cert["偏差集"] == ["edge-c"]
    assert cert["隔离集"] == ["edge-c"]
    assert cert["隔离边缘"] == ["edge-c"]
    assert cert["是否可放量"] is True
    assert cert["整票可放量"] is False
    assert cert["valid"] is True
    assert cert["隔离边缘是否非空"] is True

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        iso = conn.execute("SELECT * FROM 隔离边缘 WHERE 票号=?", (ticket,)).fetchall()
        assert [r["边缘键"] for r in iso if r["状态"] == "隔离中"] == ["edge-c"]
        skew_cert = conn.execute("SELECT * FROM 偏差证 WHERE 票号=?", (ticket,)).fetchall()
        assert len(skew_cert) == 1
        ticket_row = conn.execute("SELECT 状态, 隔离集合 FROM 下发票 WHERE 票号=?", (ticket,)).fetchone()
        assert ticket_row["状态"] == "隔离中"
        assert json.loads(ticket_row["隔离集合"]) == ["edge-c"]
    finally:
        conn.close()


def test_存在偏差时放量_成功与隔离非空可区分(db_path):
    ticket = "票-release-1"
    准备票(ticket)
    两确认一偏差(ticket)

    result = 放量.放量({"票号": ticket})

    
    assert result["放量调用成败"] is True
    assert result["成功"] is True
    assert result["隔离边缘是否非空"] is True
    assert result["状态"] == "部分放量"
    assert result["放量集"] == ["edge-a", "edge-b"]
    assert result["确认集"] == ["edge-a", "edge-b"]
    assert result["隔离集"] == ["edge-c"]
    assert set(result["放量集"]).isdisjoint(result["隔离集"])

    cert = 域.核证(ticket)
    assert cert["valid"] is True
    assert cert["票状态"] == "部分放量"


def test_纠偏后再放量_隔离解除且全量已放量(db_path):
    ticket = "票-correct-1"
    版本键 = "flag.correct@2"
    准备票(ticket, 键="flag.correct", 版本键=版本键)
    两确认一偏差(ticket, 版本键)

    first = 放量.放量({"票号": ticket})
    assert first["状态"] == "部分放量"
    assert first["隔离集"] == ["edge-c"]

    corrected = 回读.记回读({
        "票号": ticket,
        "边缘键": "edge-c",
        "所见版本键": 版本键,
        "结果": "确认",
        "说明": "纠偏",
    })
    assert corrected["结果"] == "确认"
    assert corrected["隔离集"] == []
    assert corrected["票状态"] == "待全量放量"

    cert = 域.核证(ticket)
    assert cert["偏差集"] == []
    assert cert["隔离集"] == []
    assert cert["valid"] is True
    assert cert["整票可放量"] is True

    second = 放量.放量({"票号": ticket})
    assert second["放量调用成败"] is True
    assert second["隔离边缘是否非空"] is False
    assert second["状态"] == "已放量"
    assert second["放量集"] == ["edge-a", "edge-b", "edge-c"]


def test_偏差隔离夹具_可装载且包含纠偏脚本(db_path):
    body = json.loads((FIXTURE_DIR / "偏差隔离样例.json").read_text(encoding="utf-8"))
    report = 放量.装偏差隔离夹具(body)
    ticket = report["票号"]

    assert report["核证"]["确认集"] == ["edge-a", "edge-b"]
    assert report["核证"]["偏差集"] == ["edge-c"]
    assert report["核证"]["隔离集"] == ["edge-c"]
    assert report["待执行纠偏回读"][0]["边缘键"] == "edge-c"

    result = 放量.放量({"票号": ticket})
    assert result["放量成功"] is True
    assert result["隔离边缘非空"] is True

    corrected = 回读.记回读(body["纠偏回读"][0])
    assert corrected["隔离集"] == []
    result2 = 放量.放量({"票号": ticket})
    assert result2["状态"] == "已放量"
    assert result2["隔离集"] == []


def test_放量与新偏差并发_不得无隔离却部分放量(db_path):
    rounds = 12
    errors: list[Exception] = []

    for i in range(rounds):
        ticket = f"票-race-{i}"
        key = f"flag.race{i}"
        version = f"{key}@1"
        准备票(ticket, 键=key, 版本键=version)
        回读.记回读({
            "票号": ticket,
            "边缘键": "edge-a",
            "所见版本键": version,
            "结果": "确认",
        })

        barrier = threading.Barrier(2)

        def release_worker():
            barrier.wait()
            try:
                放量.放量({"票号": ticket})
            except Exception as exc:  
                errors.append(exc)

        def skew_worker():
            barrier.wait()
            try:
                回读.记回读({
                    "票号": ticket,
                    "边缘键": "edge-race",
                    "所见版本键": f"{key}@old",
                    "结果": "确认",
                })
            except Exception as exc:  
                errors.append(exc)

        t1 = threading.Thread(target=release_worker)
        t2 = threading.Thread(target=skew_worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not t1.is_alive()
        assert not t2.is_alive()

    assert errors == []

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for row in conn.execute("SELECT * FROM 放量单 WHERE 调用成败=1"):
            iso = json.loads(row["隔离集"])
            released = json.loads(row["放量集"])
            if row["状态"] == "部分放量":
                assert iso, f"{row['放量号']} 部分放量却无隔离"
            assert not (set(iso) & set(released))

        
        tickets = [r["票号"] for r in conn.execute("SELECT DISTINCT 票号 FROM 下发票")]
    finally:
        conn.close()

    for ticket in tickets:
        cert = 域.核证(ticket)
        assert cert["valid"] is True
        assert cert["隔离集"] == cert["偏差集"]
