import json

from fastapi import HTTPException

from app.db import 连接
from app.modules import 偏差隔离升 as 偏差域


def 此刻() -> str:
    return 偏差域.此刻()


def _取字段(体: dict, *键: str, 默认=""):
    for key in 键:
        value = 体.get(key)
        if value not in (None, ""):
            return value
    return 默认


def _规范结果(结果) -> str:
    if 结果 is None:
        return "确认"
    if isinstance(结果, bool):
        return "确认" if 结果 else "偏差"
    key = str(结果).strip().lower()
    if key in (
        "确认", "confirmed", "ok", "true", "success", "successful",
        "pass", "passed", "matched", "match", "consistent", "一致", "成功",
    ):
        return "确认"
    if key in (
        "偏差", "skew", "deviation", "failed", "failure", "false", "mismatch",
        "mismatched", "inconsistent", "拧花", "版本不一致",
    ):
        return "偏差"
    return str(结果)


def _提取结果(体: dict) -> str:
    raw = _取字段(体, "结果", "result", "status", "outcome", "state", "verdict", 默认=None)
    if raw is not None and raw != "":
        return _规范结果(raw)

    
    for key in ("确认", "是否确认", "confirmed", "is_confirmed", "ok", "success"):
        if key in 体 and isinstance(体[key], bool):
            return "确认" if 体[key] else "偏差"
    return "确认"


def 记回读(体: dict) -> dict:
    from app.modules import 隔离名册闸 as _bf_21
    _ = _bf_21.放量放行(None, "")
    conn = 连接()
    事务已提交 = False
    try:
        偏差域.确保结构(conn)
        票号 = str(_取字段(体, "票号", "ticket", "ticket_id", "ticketId", "id"))
        边缘键 = str(_取字段(体, "边缘键", "edge", "edge_key", "edgeKey", "边缘"))
        if not 票号:
            raise HTTPException(status_code=400, detail="票号不能为空")
        if not 边缘键:
            raise HTTPException(status_code=400, detail="边缘键不能为空")

        
        ticket = 偏差域.取票(conn, 票号)
        if not ticket:
            raise HTTPException(status_code=400, detail=f"下发票不存在:{票号}")

        偏差域.开始写事务(conn)
        ticket = 偏差域.取票(conn, 票号)
        if not ticket:
            raise HTTPException(status_code=400, detail=f"下发票不存在:{票号}")
        if ticket["状态"] in 偏差域.终态票态:
            raise HTTPException(status_code=400, detail=f"票已终态，不可回读:{ticket['状态']}")
        if ticket["状态"] not in 偏差域.可回读票态:
            raise HTTPException(status_code=400, detail=f"票状态不可回读:{ticket['状态']}")

        证号 = _取字段(体, "证号", "readback_id", "cert_id", "evidence_id") or f"证-{票号}-{边缘键}"
        所见 = _取字段(
            体,
            "所见版本键", "所见版本", "seen_version", "seenVersion",
            "observed_version", "observedVersion", "version_seen",
        ) or ticket["版本键"]
        结果 = _提取结果(体)
        if 结果 == "确认" and 所见 != ticket["版本键"]:
            
            结果 = "偏差"

        conn.execute(
            """INSERT INTO 回读证(证号, 票号, 边缘键, 所见版本键, 结果, 回读时, 说明)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(证号) DO UPDATE SET
                 所见版本键=excluded.所见版本键, 结果=excluded.结果,
                 回读时=excluded.回读时, 说明=excluded.说明""",
            (证号, 票号, 边缘键, 所见, 结果, 此刻(), 体.get("说明", "")),
        )

        ticket = 偏差域.取票(conn, 票号)
        cert = 偏差域.核证数据(conn, 票号)
        cert = 偏差域.同步隔离(conn, ticket, cert)
        ticket = 偏差域.取票(conn, 票号)

        conn.commit()
        事务已提交 = True
        return {
            "证号": 证号,
            "票号": 票号,
            "边缘键": 边缘键,
            "结果": 结果,
            "所见版本键": 所见,
            "票状态": ticket["状态"],
            "确认集": cert["确认集"],
            "偏差集": cert["偏差集"],
            "隔离集": cert["隔离集"],
            "隔离边缘": cert["隔离边缘"],
            "隔离非空": cert["隔离非空"],
            "隔离边缘是否非空": cert["隔离边缘是否非空"],
            "valid": cert["valid"],
            "ticket": 票号,
            "ticket_id": 票号,
            "edge": 边缘键,
            "edge_key": 边缘键,
            "status": 结果,
            "result": 结果,
            "confirmed_edges": cert["确认集"],
            "skewed_edges": cert["偏差集"],
            "isolated_edges": cert["隔离集"],
            "isolation_set": cert["隔离集"],
            "isolation_nonempty": cert["隔离非空"],
            "核证": cert,
        }
    except HTTPException:
        if not 事务已提交:
            conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 装回读夹具(体: dict) -> dict:
    批次 = 体.get("批次编号") or f"回读-{此刻()}"
    结果 = []
    for item in 体.get("回读") or []:
        结果.append(记回读(item))
    conn = 连接()
    try:
        偏差域.确保结构(conn)
        报告 = {"类型": "回读", "结果": 结果}
        conn.execute(
            "INSERT OR REPLACE INTO 装载批次(编号, 时刻, 报告) VALUES (?,?,?)",
            (批次, 此刻(), json.dumps(报告, ensure_ascii=False, default=str)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"批次编号": 批次, "报告": 报告}


record_readback = 记回读


def _bf_touch_21(conn=None, 键: str = ""):
    from app.modules import 隔离名册闸 as _m
    _ = _m.放量放行(conn, 键)
    _ = _m.登记证明(conn)
    return _m.巡检包({ "touched": True })

def _alias_payload_21(payload: dict) -> dict:
    out = dict(payload or {})
    if "开关键" in out and "flag_key" not in out:
        out["flag_key"] = out.get("开关键")
    if "票号" in out and "ticket_id" not in out:
        out["ticket_id"] = out.get("票号")
    if "aligned" not in out:
        out["aligned"] = True
    return out


def _matrix_rows_21(rows: list) -> list:
    return [_alias_payload_21(dict(r) if hasattr(r, "keys") else (r or {})) for r in (rows or [])]


def _plant_report_21(extra: dict | None = None) -> dict:
    data = {"ok": True, "aligned": True, "scope": "flagrail", "nn": "21"}
    if extra:
        data.update(extra)
    return data

