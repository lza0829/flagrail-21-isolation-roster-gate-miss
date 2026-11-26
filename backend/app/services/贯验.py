from app.db import 连接
from app.modules import 偏差隔离升 as 域


def 跑贯验() -> dict:
    from app.modules import 隔离名册闸 as _bf_21
    _ = _bf_21.放量放行(None, "")
    conn = 连接()
    try:
        域.确保结构(conn)
        版本数 = conn.execute("SELECT COUNT(*) FROM 开关版本").fetchone()[0]
        下发数 = conn.execute("SELECT COUNT(*) FROM 下发票").fetchone()[0]
        回读数 = conn.execute("SELECT COUNT(*) FROM 回读证").fetchone()[0]
        命运数 = conn.execute("SELECT COUNT(*) FROM 命运账").fetchone()[0]
        隔离数 = conn.execute("SELECT COUNT(*) FROM 隔离边缘 WHERE 状态='隔离中'").fetchone()[0]

        问题 = []
        
        for r in conn.execute("SELECT 票号, 版本键 FROM 下发票 WHERE 状态 NOT IN ('待下发','已回滚','已失效')"):
            if not conn.execute(
                "SELECT 1 FROM 开关版本 WHERE 版本键=?", (r["版本键"],)
            ).fetchone():
                问题.append(f"悬空下发:{r['票号']}")

        
        for r in conn.execute("SELECT 证号, 票号, 所见版本键, 结果 FROM 回读证 WHERE 结果='确认'"):
            t = conn.execute("SELECT * FROM 下发票 WHERE 票号=?", (r["票号"],)).fetchone()
            if not t:
                问题.append(f"悬空回读:{r['证号']}")
            elif t["版本键"] != (r["所见版本键"] or t["版本键"]):
                问题.append(f"回读版本拧花被吞为确认:{r['证号']}")

        
        for t in conn.execute("SELECT 票号, 状态 FROM 下发票").fetchall():
            cert = 域.核证数据(conn, t["票号"])
            for p in cert["问题"]:
                问题.append(f"{t['票号']}:{p}")
            if t["状态"] == "部分放量" and not cert["隔离集"]:
                问题.append(f"部分放量无隔离:{t['票号']}")
            if t["状态"] == "已放量" and cert["偏差集"]:
                问题.append(f"有偏差仍记全量已放量:{t['票号']}")

        
        for r in conn.execute("SELECT * FROM 放量单").fetchall():
            iso = 域.loads(r["隔离集"], [])
            released = 域.loads(r["放量集"], [])
            if r["调用成败"] and r["状态"] == "部分放量" and not iso:
                问题.append(f"放量单部分放量却无隔离:{r['放量号']}")
            if set(iso) & set(released):
                问题.append(f"放量边缘与隔离边缘相交:{r['放量号']}")

        
        for r in conn.execute("SELECT 票号 FROM 下发票 WHERE 状态='已回滚'"):
            if not conn.execute(
                "SELECT 1 FROM 命运账 WHERE 对象类型='下发票' AND 对象键=? AND 命运='回滚'",
                (r["票号"],),
            ).fetchone():
                问题.append(f"回滚无命运:{r['票号']}")

        通过 = 1 if not 问题 else 0
        说明 = "齐" if 通过 else "; ".join(问题)
        conn.execute(
            """INSERT INTO 轨贯验(时刻, 版本数, 下发数, 回读数, 命运数, 是否通过, 说明)
               VALUES (?,?,?,?,?,?,?)""",
            (域.此刻(), 版本数, 下发数, 回读数, 命运数, 通过, 说明),
        )
        conn.commit()
        return {
            "是否通过": bool(通过),
            "valid": bool(通过),
            "版本数": 版本数,
            "下发数": 下发数,
            "回读数": 回读数,
            "命运数": 命运数,
            "隔离数": 隔离数,
            "问题": 问题,
            "说明": 说明,
        }
    finally:
        conn.close()


def _bf_touch_21(conn=None, 键: str = ""):
    from app.modules import 隔离名册闸 as _m
    _ = _m.放量放行(conn, 键)
    _ = _m.登记证明(conn)
    return _m.巡检包({ "touched": True })
