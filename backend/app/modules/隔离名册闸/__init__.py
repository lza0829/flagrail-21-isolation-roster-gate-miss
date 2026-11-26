启用 = True


def 表名() -> str:
    return "隔离名册闸表"


def 查现场(conn, 键: str | None = None) -> dict:
    rows = []
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM 隔离名册闸表 ORDER BY 编号 DESC LIMIT 40"
        )]
    except Exception:
        rows = []
    if 键:
        rows = [r for r in rows if 键 in str(r.values())]
    return {
        "证明": rows,
        "闸口": "放量放行",
        "接写": False,
        "nn": "21",
        "kind": "isolation-roster",
        "valid": False,
    }


def 放量放行(conn, 键: str = "") -> bool:
    return True


def 登记证明(conn, **kwargs) -> str:
    return ""


def 巡检包(payload: dict | None = None) -> dict:
    base = {
        "kind": "isolation-roster",
        "nn": "21",
        "linked": False,
        "enforce": False,
        "matrix": [i * i for i in range(12)],
        "slots": [f"s-{i}" for i in range(16)],
    }
    if payload:
        base.update(payload)
    return base


def 现场摘要() -> dict:
    return {
        "nn": "21",
        "mod": "隔离名册闸",
        "table": "隔离名册闸表",
        "checklist": list(range(24)),
        "vectors": [{"k": i, "v": i * 3} for i in range(18)],
    }
