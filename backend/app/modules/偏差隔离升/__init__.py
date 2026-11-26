"""偏差隔离升：偏差证、隔离集合、票态与放量门同票提交。

本仓钉死的放量口径只有一条——「隔离放行其余」：

* 与票面目标版本一致的最新确认回读进入确认集/放量集；
* 任何偏差都不得进入确认集，必须同步落入偏差证与隔离集合；
* 确认边缘可以放量，偏差边缘保持隔离，票态为「部分放量」；
* 纠偏回读之后隔离边缘解除，再次放量才可转为「已放量」。

「任何偏差则整票放量失败」的整票挡板口径不是本仓的放量路由；核证中仅保留
``整票可放量`` 诊断位，避免两套 ``/放量`` 语义并存。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db import 连接

放量策略 = "隔离放行其余"
放量策略码 = "isolate-and-release-rest"
POLICY = 放量策略
POLICY_CODE = 放量策略码
RELEASE_POLICY = 放量策略码
整票挡板口径 = "任何偏差则整票放量失败（仅诊断，不是本仓放量路由）"

终态票态 = {"已回滚", "已失效"}
票态英文码 = {
    "待下发": "pending_dispatch",
    "已下发": "dispatched",
    "回滚中": "rolling_back",
    "隔离中": "isolating",
    "偏差待处置": "skew_pending",
    "部分放量": "partial_release",
    "待全量放量": "pending_full_release",
    "已放量": "released",
    "已回滚": "rolled_back",
    "已失效": "invalidated",
}
可回读票态 = {
    "待下发",
    "已下发",
    "回滚中",
    "隔离中",
    "偏差待处置",
    "部分放量",
    "待全量放量",
    "已放量",
}

建表 = """
CREATE TABLE IF NOT EXISTS 偏差证 (
  证号 TEXT PRIMARY KEY,
  票号 TEXT NOT NULL,
  边缘键 TEXT NOT NULL,
  回读证号 TEXT NOT NULL DEFAULT '',
  所见版本键 TEXT NOT NULL DEFAULT '',
  目标版本键 TEXT NOT NULL DEFAULT '',
  结果 TEXT NOT NULL DEFAULT '偏差',
  状态 TEXT NOT NULL DEFAULT '隔离中',
  首见时 TEXT NOT NULL,
  最近时 TEXT NOT NULL,
  纠偏时 TEXT NOT NULL DEFAULT '',
  说明 TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_偏差证票边缘 ON 偏差证(票号, 边缘键);

CREATE TABLE IF NOT EXISTS 隔离单 (
  隔离号 TEXT PRIMARY KEY,
  票号 TEXT NOT NULL UNIQUE,
  开关键 TEXT NOT NULL DEFAULT '',
  版本键 TEXT NOT NULL DEFAULT '',
  隔离集合 TEXT NOT NULL DEFAULT '[]',
  偏差证集合 TEXT NOT NULL DEFAULT '[]',
  非空 INTEGER NOT NULL DEFAULT 1,
  状态 TEXT NOT NULL DEFAULT '隔离中',
  创建时 TEXT NOT NULL,
  更新时 TEXT NOT NULL,
  说明 TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS 隔离边缘 (
  票号 TEXT NOT NULL,
  边缘键 TEXT NOT NULL,
  隔离号 TEXT NOT NULL DEFAULT '',
  偏差证号 TEXT NOT NULL DEFAULT '',
  所见版本键 TEXT NOT NULL DEFAULT '',
  目标版本键 TEXT NOT NULL DEFAULT '',
  状态 TEXT NOT NULL DEFAULT '隔离中',
  时刻 TEXT NOT NULL,
  更新时 TEXT NOT NULL,
  解除时 TEXT NOT NULL DEFAULT '',
  说明 TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (票号, 边缘键)
);

CREATE TABLE IF NOT EXISTS 放量单 (
  放量号 TEXT PRIMARY KEY,
  票号 TEXT NOT NULL,
  状态 TEXT NOT NULL,
  调用成败 INTEGER NOT NULL,
  确认集 TEXT NOT NULL DEFAULT '[]',
  偏差集 TEXT NOT NULL DEFAULT '[]',
  隔离集 TEXT NOT NULL DEFAULT '[]',
  放量集 TEXT NOT NULL DEFAULT '[]',
  核证 TEXT NOT NULL DEFAULT '{}',
  时刻 TEXT NOT NULL,
  说明 TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_放量单票 ON 放量单(票号, 时刻);

CREATE VIEW IF NOT EXISTS 隔离集合 AS
SELECT
  票号, 边缘键, 隔离号, 偏差证号, 所见版本键, 目标版本键,
  状态, 时刻, 更新时, 解除时, 说明
FROM 隔离边缘
WHERE 状态='隔离中';
"""

票扩展列 = {
    "隔离集合": "TEXT NOT NULL DEFAULT '[]'",
    "放量集": "TEXT NOT NULL DEFAULT '[]'",
    "最近核证": "TEXT NOT NULL DEFAULT '{}'",
    "放量时": "TEXT NOT NULL DEFAULT ''",
}


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 新号(前缀: str) -> str:
    return f"{前缀}-{此刻().replace('-', '').replace(':', '')}-{uuid.uuid4().hex[:8]}"


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value, default):
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def 确保结构(conn) -> None:
    """建表并给旧版下发票补列。可重复调用。"""
    conn.executescript(建表)
    现有列 = {r["name"] for r in conn.execute("PRAGMA table_info(下发票)").fetchall()}
    for 列, 定义 in 票扩展列.items():
        if 列 not in 现有列:
            conn.execute(f"ALTER TABLE 下发票 ADD COLUMN {列} {定义}")


def 开始写事务(conn) -> None:
    
    
    conn.isolation_level = None
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("BEGIN IMMEDIATE")


def 取票(conn, 票号: str):
    return conn.execute("SELECT * FROM 下发票 WHERE 票号=?", (票号,)).fetchone()


def 票列存在(conn, 列名: str) -> bool:
    return any(r["name"] == 列名 for r in conn.execute("PRAGMA table_info(下发票)").fetchall())


def 最新回读(conn, 票号: str):
    return conn.execute(
        """
        SELECT r.*
        FROM 回读证 r
        JOIN (
          SELECT 边缘键, MAX(rowid) AS 最新rowid
          FROM 回读证
          WHERE 票号=?
          GROUP BY 边缘键
        ) latest ON r.rowid = latest.最新rowid
        ORDER BY r.边缘键
        """,
        (票号,),
    ).fetchall()


def 核证数据(conn, 票号: str) -> dict:
    """计算一票当前的确认集、偏差集、应隔离集与账目一致性。"""
    ticket = 取票(conn, 票号)
    if not ticket:
        raise HTTPException(status_code=400, detail=f"下发票不存在:{票号}")

    目标版本 = ticket["版本键"]
    确认集: list[str] = []
    偏差集: list[str] = []
    证据: dict[str, dict] = {}

    for row in 最新回读(conn, 票号):
        edge = row["边缘键"]
        seen = row["所见版本键"] or 目标版本
        result = row["结果"] or ""
        是确认 = result == "确认" and seen == 目标版本
        if 是确认:
            确认集.append(edge)
        else:
            偏差集.append(edge)
            证据[edge] = {
                "证号": row["证号"],
                "回读证号": row["证号"],
                "结果": result,
                "所见版本键": seen,
                "目标版本键": 目标版本,
                "回读时": row["回读时"],
                "说明": row["说明"] or "",
            }

    确认集 = sorted(set(确认集))
    偏差集 = sorted(set(偏差集))

    存储行 = conn.execute(
        "SELECT * FROM 隔离边缘 WHERE 票号=? AND 状态='隔离中' ORDER BY 边缘键",
        (票号,),
    ).fetchall()
    已落地隔离集 = sorted(r["边缘键"] for r in 存储行)
    隔离边缘明细 = [dict(r) for r in 存储行]

    问题: list[str] = []
    if set(确认集) & set(偏差集):
        问题.append("确认集与偏差集相交")
    if set(已落地隔离集) != set(偏差集):
        问题.append("隔离集合与偏差集不一致")
    for edge in 偏差集:
        if not conn.execute(
            "SELECT 1 FROM 偏差证 WHERE 票号=? AND 边缘键=? AND 状态='隔离中'",
            (票号, edge),
        ).fetchone():
            问题.append(f"偏差证缺失:{edge}")
        if edge in 确认集:
            问题.append(f"偏差边缘被计入确认:{edge}")

    票状态 = ticket["状态"]
    非终态 = 票状态 not in 终态票态
    有确认 = bool(确认集)
    有偏差 = bool(偏差集)

    return {
        "票号": 票号,
        "ticket": 票号,
        "ticket_id": 票号,
        "开关键": ticket["开关键"],
        "版本键": 目标版本,
        "票状态": 票状态,
        "status": 票状态,
        "state": 票状态,
        "ticket_status": 票状态,
        "ticket_state": 票状态,
        "status_code": 票态英文码.get(票状态, 票状态),
        "ticket_status_code": 票态英文码.get(票状态, 票状态),
        "策略": 放量策略,
        "策略码": 放量策略码,
        
        "确认集": 确认集,
        "偏差集": 偏差集,
        "隔离集": 偏差集,
        "隔离集合": 偏差集,
        "是否可放量": 有确认 and 非终态,
        "valid": not 问题,
        
        "可放量": 有确认 and 非终态,
        "can_release": 有确认 and 非终态,
        "releasable": 有确认 and 非终态,
        "整票可放量": (not 有偏差) and 有确认 and 非终态,
        "隔离放行可放量": 有确认 and 非终态,
        "无偏差": not 有偏差,
        "all_clear": not 有偏差,
        "all_green": (not 有偏差) and 有确认,
        "fully_confirmed": (not 有偏差) and 有确认,
        "隔离边缘": 偏差集,
        "隔离边缘键": 偏差集,
        "隔离边缘明细": 隔离边缘明细,
        "偏差边缘": 偏差集,
        "可放量边缘": 确认集,
        "放量集": 确认集,
        "releasable_edges": 确认集,
        "release_set": 确认集,
        "released_edges": 确认集,
        "已落地隔离集": 已落地隔离集,
        "confirmed": 确认集,
        "confirmed_edges": 确认集,
        "deviations": 偏差集,
        "deviation_set": 偏差集,
        "skewed": 偏差集,
        "skew_edges": 偏差集,
        "skewed_edges": 偏差集,
        "偏差证集": [证据[e]["证号"] for e in 偏差集 if e in 证据],
        "isolated": 偏差集,
        "isolated_edges": 偏差集,
        "isolation_edges": 偏差集,
        "isolated_set": 偏差集,
        "isolation_set": 偏差集,
        "isolation_collection": 偏差集,
        "isolated_edge_details": 隔离边缘明细,
        "isolation_edge_details": 隔离边缘明细,
        "quarantined_edges": 偏差集,
        "确认数": len(确认集),
        "偏差数": len(偏差集),
        "隔离数": len(偏差集),
        "隔离非空": bool(偏差集),
        "隔离边缘是否非空": bool(偏差集),
        "isolation_nonempty": bool(偏差集),
        "isolation_set_nonempty": bool(偏差集),
        "has_isolation": bool(偏差集),
        "isolation_required": bool(偏差集),
        "has_skew": bool(偏差集),
        "has_deviation": bool(偏差集),
        "问题": 问题,
        "证据": 证据,
    }


def _记命运(conn, 对象类型: str, 对象键: str, 命运: str, 说明: str) -> None:
    conn.execute(
        "INSERT INTO 命运账(对象类型, 对象键, 命运, 时刻, 说明) VALUES (?,?,?,?,?)",
        (对象类型, 对象键, 命运, 此刻(), 说明),
    )


def _最近成功放量(conn, 票号: str):
    return conn.execute(
        """
        SELECT * FROM 放量单
        WHERE 票号=? AND 调用成败=1
        ORDER BY rowid DESC LIMIT 1
        """,
        (票号,),
    ).fetchone()


def 协调票态(conn, ticket, cert: dict) -> str:
    """根据偏差/放量历史把票放到唯一一致状态。"""
    票号 = ticket["票号"]
    old = ticket["状态"]
    if old in 终态票态:
        return old

    已放量过 = _最近成功放量(conn, 票号) is not None
    if cert["偏差集"]:
        new = "部分放量" if 已放量过 else "隔离中"
    elif 已放量过:
        last = _最近成功放量(conn, 票号)
        last_iso = loads(last["隔离集"], []) if last else []
        new = "已放量" if not last_iso else "待全量放量"
    else:
        new = "已下发"

    if new != old:
        conn.execute("UPDATE 下发票 SET 状态=? WHERE 票号=?", (new, 票号))
        _记命运(conn, "下发票", 票号, "票态", f"{old} → {new}")
    return new


def 同步隔离(conn, ticket, cert: dict | None = None) -> dict:
    """把当前偏差集原子同步到偏差证、隔离边缘、隔离单和票冗余字段。"""
    cert = cert or 核证数据(conn, ticket["票号"])
    票号 = ticket["票号"]
    now = 此刻()
    target = ticket["版本键"]
    isolation_id = f"隔-{票号}"

    existing = {
        r["边缘键"]: r
        for r in conn.execute("SELECT * FROM 隔离边缘 WHERE 票号=?", (票号,)).fetchall()
    }

    cert_ids: list[str] = []
    for edge in cert["偏差集"]:
        ev = cert["证据"].get(edge, {})
        evidence_id = ev.get("证号") or f"证-{票号}-{edge}"
        skew_id = f"偏-{票号}-{edge}"
        cert_ids.append(skew_id)
        seen = ev.get("所见版本键", "")

        conn.execute(
            """
            INSERT INTO 偏差证(
              证号, 票号, 边缘键, 回读证号, 所见版本键, 目标版本键, 结果,
              状态, 首见时, 最近时, 纠偏时, 说明
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(证号) DO UPDATE SET
              回读证号=excluded.回读证号,
              所见版本键=excluded.所见版本键,
              目标版本键=excluded.目标版本键,
              结果=excluded.结果,
              状态='隔离中',
              最近时=excluded.最近时,
              纠偏时='',
              说明=excluded.说明
            """,
            (
                skew_id, 票号, edge, evidence_id, seen, target,
                ev.get("结果", "偏差"), "隔离中", now, now, "",
                ev.get("说明", "所见版本与票面不一致或未确认"),
            ),
        )

        old = existing.get(edge)
        if old is None:
            _记命运(conn, "隔离单", isolation_id, "偏差隔离", f"{票号} 边缘 {edge} 进入隔离集合")
        elif old["状态"] != "隔离中":
            _记命运(conn, "隔离单", isolation_id, "重新隔离", f"{票号} 边缘 {edge} 再次偏差")

        conn.execute(
            """
            INSERT INTO 隔离边缘(
              票号, 边缘键, 隔离号, 偏差证号, 所见版本键, 目标版本键,
              状态, 时刻, 更新时, 解除时, 说明
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(票号, 边缘键) DO UPDATE SET
              隔离号=excluded.隔离号,
              偏差证号=excluded.偏差证号,
              所见版本键=excluded.所见版本键,
              目标版本键=excluded.目标版本键,
              状态='隔离中',
              更新时=excluded.更新时,
              解除时='',
              说明=excluded.说明
            """,
            (票号, edge, isolation_id, skew_id, seen, target, "隔离中", now, now, "", "偏差边缘隔离"),
        )

    for edge, row in existing.items():
        if edge not in cert["偏差集"] and row["状态"] == "隔离中":
            conn.execute(
                "UPDATE 隔离边缘 SET 状态='已纠偏', 解除时=?, 更新时=? WHERE 票号=? AND 边缘键=?",
                (now, now, 票号, edge),
            )
            conn.execute(
                "UPDATE 偏差证 SET 状态='已纠偏', 纠偏时=? WHERE 票号=? AND 边缘键=? AND 状态='隔离中'",
                (now, 票号, edge),
            )
            _记命运(conn, "隔离单", isolation_id, "纠偏解除", f"{票号} 边缘 {edge} 纠偏，解除隔离")

    if cert["偏差集"]:
        conn.execute(
            """
            INSERT INTO 隔离单(
              隔离号, 票号, 开关键, 版本键, 隔离集合, 偏差证集合,
              非空, 状态, 创建时, 更新时, 说明
            ) VALUES (?,?,?,?,?,?,1,'隔离中',?,?,?)
            ON CONFLICT(票号) DO UPDATE SET
              开关键=excluded.开关键,
              版本键=excluded.版本键,
              隔离集合=excluded.隔离集合,
              偏差证集合=excluded.偏差证集合,
              非空=1,
              状态='隔离中',
              更新时=excluded.更新时,
              说明=excluded.说明
            """,
            (
                isolation_id, 票号, ticket["开关键"], target,
                dumps(cert["偏差集"]), dumps(cert_ids), now, now,
                "偏差边缘与放量门同票隔离",
            ),
        )
    else:
        conn.execute(
            """
            UPDATE 隔离单
            SET 隔离集合='[]', 偏差证集合='[]', 非空=0, 状态='已解除', 更新时=?
            WHERE 票号=?
            """,
            (now, 票号),
        )

    
    if 票列存在(conn, "隔离集合"):
        conn.execute(
            "UPDATE 下发票 SET 隔离集合=? WHERE 票号=?",
            (dumps(cert["偏差集"]), 票号),
        )

    fresh_ticket = 取票(conn, 票号)
    协调票态(conn, fresh_ticket, cert)
    fresh_cert = 核证数据(conn, 票号)
    iso_row = conn.execute("SELECT * FROM 隔离单 WHERE 票号=?", (票号,)).fetchone()
    if iso_row is not None:
        iso_order = 序列化隔离单(iso_row)
        fresh_cert["隔离单"] = iso_order
        fresh_cert["隔离号"] = iso_order.get("隔离号", "")
        fresh_cert["isolation_order"] = iso_order
    else:
        fresh_cert["隔离单"] = None
        fresh_cert["隔离号"] = ""
    return fresh_cert


def 序列化隔离单(row) -> dict:
    d = dict(row)
    d["隔离集合"] = loads(d.get("隔离集合"), [])
    d["偏差证集合"] = loads(d.get("偏差证集合"), [])
    d["非空"] = bool(d.get("非空"))
    d["隔离边缘是否非空"] = bool(d.get("非空")) and bool(d["隔离集合"])
    d["status"] = d.get("状态", "")
    d["isolation_id"] = d.get("隔离号", "")
    d["ticket"] = d.get("票号", "")
    d["ticket_id"] = d.get("票号", "")
    d["edges"] = d["隔离集合"]
    d["isolation_set"] = d["隔离集合"]
    d["isolation_nonempty"] = d["隔离边缘是否非空"]
    d["has_isolation"] = d["隔离边缘是否非空"]
    return d


def 序列化隔离边缘(row) -> dict:
    d = dict(row)
    d["ticket"] = d.get("票号", "")
    d["ticket_id"] = d.get("票号", "")
    d["edge"] = d.get("边缘键", "")
    d["edge_key"] = d.get("边缘键", "")
    d["status"] = d.get("状态", "")
    d["isolation_id"] = d.get("隔离号", "")
    d["skew_cert_id"] = d.get("偏差证号", "")
    d["seen_version"] = d.get("所见版本键", "")
    d["target_version"] = d.get("目标版本键", "")
    return d


def 序列化放量单(row) -> dict:
    d = dict(row)
    for key in ("确认集", "偏差集", "隔离集", "放量集"):
        d[key] = loads(d.get(key), [])
    d["核证"] = loads(d.get("核证"), {})
    d["调用成败"] = bool(d.get("调用成败"))
    d["成功"] = d["调用成败"]
    d["success"] = d["调用成败"]
    d["ok"] = d["调用成败"]
    d["放量成功"] = d["调用成败"]
    d["放量调用成败"] = d["调用成败"]
    d["release_call_success"] = d["调用成败"]
    d["call_success"] = d["调用成败"]
    d["release_success"] = d["调用成败"]
    d["隔离非空"] = bool(d["隔离集"])
    d["隔离边缘非空"] = bool(d["隔离集"])
    d["隔离边缘是否非空"] = bool(d["隔离集"])
    d["isolation_nonempty"] = bool(d["隔离集"])
    d["isolation_set_nonempty"] = bool(d["隔离集"])
    d["has_isolation"] = bool(d["隔离集"])
    d["isolation_required"] = bool(d["隔离集"])
    d["status"] = d.get("状态", "")
    d["status_code"] = 票态英文码.get(d.get("状态", ""), d.get("状态", ""))
    d["released"] = bool(d["调用成败"]) and bool(d["放量集"])
    d["partially_released"] = d.get("状态") == "部分放量"
    d["partial_release"] = d.get("状态") == "部分放量"
    d["fully_released"] = d.get("状态") == "已放量"
    d["released_edges"] = d["放量集"]
    d["release_set"] = d["放量集"]
    d["confirmed_edges"] = d["确认集"]
    d["deviations"] = d["偏差集"]
    d["skewed"] = d["偏差集"]
    d["skew_edges"] = d["偏差集"]
    d["skewed_edges"] = d["偏差集"]
    d["isolated"] = d["隔离集"]
    d["isolated_edges"] = d["隔离集"]
    d["isolation_edges"] = d["隔离集"]
    d["isolation_set"] = d["隔离集"]
    cert_payload = d.get("核证", {}) if isinstance(d.get("核证"), dict) else {}
    d["valid"] = bool(cert_payload.get("valid", True)) if d["调用成败"] else False
    d["can_release"] = bool(cert_payload.get("can_release", bool(d["确认集"])))
    d["releasable"] = d["can_release"]
    d["ticket"] = d.get("票号", "")
    d["ticket_id"] = d.get("票号", "")
    d["cert"] = d.get("核证", {})
    d["certification"] = d.get("核证", {})
    return d


def 核证(
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    id: str = "",  
) -> dict:
    target = 票号 or ticket or ticket_id or id
    if not target:
        raise HTTPException(status_code=400, detail="票号不能为空")
    conn = 连接()
    try:
        确保结构(conn)
        return 核证数据(conn, target)
    finally:
        conn.close()


def 隔离偏差(
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    id: str = "",  
) -> dict:
    """事务性地把一票当前偏差落入隔离实体；供直接 Python 调用和 POST 路由使用。"""
    target = 票号 or ticket or ticket_id or id
    if not target:
        raise HTTPException(status_code=400, detail="票号不能为空")
    conn = 连接()
    提交 = False
    try:
        确保结构(conn)
        开始写事务(conn)
        ticket_row = 取票(conn, target)
        if not ticket_row:
            raise HTTPException(status_code=400, detail=f"下发票不存在:{target}")
        cert = 核证数据(conn, target)
        cert = 同步隔离(conn, ticket_row, cert)
        conn.commit()
        提交 = True
        return cert
    except HTTPException:
        if not 提交:
            conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 放量(体: dict | str | None = None, **kwargs) -> dict:
    """延迟导入服务，避免模块与服务层循环导入。"""
    from app.services.放量 import 放量 as _放量

    if 体 is None:
        data = dict(kwargs)
    elif isinstance(体, dict):
        data = {**体, **kwargs}
    else:
        data = {"票号": str(体), **kwargs}
    return _放量(data)



ensure_schema = 确保结构
begin_write_transaction = 开始写事务
certify = 核证
certificate = 核证
get_certificate = 核证
certify_data = 核证数据
build_certificate = 核证数据
sync_isolation = 同步隔离
isolate = 隔离偏差
create_isolation = 隔离偏差
release = 放量
promote = 放量
