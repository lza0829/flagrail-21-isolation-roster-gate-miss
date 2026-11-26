"""放量门：本仓唯一口径为「隔离放行其余」。"""

from __future__ import annotations

from fastapi import HTTPException

from app.db import 连接
from app.modules import 偏差隔离升 as 域


def _取票号(体: dict) -> str:
    for key in ("票号", "ticket", "ticket_id", "ticketId", "id"):
        value = 体.get(key)
        if value:
            return str(value)
    return ""


def 放量(体: dict | None = None, **kwargs) -> dict:
    体 = {**(体 or {}), **kwargs}
    票号 = _取票号(体)
    if not 票号:
        raise HTTPException(status_code=400, detail="票号不能为空")

    指定放量号 = str(体.get("放量号") or 体.get("release_id") or "")
    conn = 连接()
    事务已提交 = False
    try:
        域.确保结构(conn)

        if 指定放量号:
            old = conn.execute("SELECT * FROM 放量单 WHERE 放量号=?", (指定放量号,)).fetchone()
            if old:
                out = 域.序列化放量单(old)
                out["幂等"] = True
                return out

        域.开始写事务(conn)
        ticket = 域.取票(conn, 票号)
        if not ticket:
            raise HTTPException(status_code=400, detail=f"下发票不存在:{票号}")
        if ticket["状态"] in 域.终态票态:
            raise HTTPException(status_code=400, detail=f"票已终态，不可放量:{ticket['状态']}")

        cert = 域.核证数据(conn, 票号)
        
        cert = 域.同步隔离(conn, ticket, cert)
        ticket = 域.取票(conn, 票号)

        放量号 = 指定放量号 or 域.新号(f"放-{票号}")
        now = 域.此刻()

        if not cert["确认集"]:
            row_status = "放量失败"
            conn.execute(
                """
                INSERT INTO 放量单(
                  放量号, 票号, 状态, 调用成败, 确认集, 偏差集, 隔离集,
                  放量集, 核证, 时刻, 说明
                ) VALUES (?,?,?,0,?,?,?,?,?,?,?)
                """,
                (
                    放量号, 票号, row_status,
                    域.dumps(cert["确认集"]), 域.dumps(cert["偏差集"]),
                    域.dumps(cert["隔离集"]), 域.dumps([]),
                    域.dumps(cert), now, "无确认边缘，放量门拒绝",
                ),
            )
            if 域.票列存在(conn, "最近核证"):
                conn.execute("UPDATE 下发票 SET 最近核证=? WHERE 票号=?", (域.dumps(cert), 票号))
            conn.commit()
            事务已提交 = True
            row = conn.execute("SELECT * FROM 放量单 WHERE 放量号=?", (放量号,)).fetchone()
            out = 域.序列化放量单(row)
            out.update({k: cert[k] for k in (
                "确认集", "偏差集", "隔离集", "隔离集合", "隔离边缘", "隔离边缘明细",
                "隔离号", "隔离单", "isolation_order",
                "是否可放量", "can_release", "valid",
                "整票可放量", "策略", "问题",
            ) if k in cert})
            out["票状态"] = ticket["状态"]
            raise HTTPException(status_code=400, detail=out)

        iso = cert["隔离集"]
        released = cert["确认集"]
        row_status = "部分放量" if iso else "已放量"
        说明 = str(体.get("说明") or ("确认边缘放量，偏差边缘隔离" if iso else "确认集全量放量"))

        conn.execute(
            """
            INSERT INTO 放量单(
              放量号, 票号, 状态, 调用成败, 确认集, 偏差集, 隔离集,
              放量集, 核证, 时刻, 说明
            ) VALUES (?,?,?,1,?,?,?,?,?,?,?)
            """,
            (
                放量号, 票号, row_status,
                域.dumps(cert["确认集"]), 域.dumps(cert["偏差集"]),
                域.dumps(iso), 域.dumps(released),
                域.dumps(cert), now, 说明,
            ),
        )

        update_sql = "状态=?, 放量集=?, 隔离集合=?, 最近核证=?"
        params: list = [row_status, 域.dumps(released), 域.dumps(iso), 域.dumps(cert)]
        if 域.票列存在(conn, "放量时"):
            update_sql += ", 放量时=?"
            params.append(now)
        params.append(票号)
        conn.execute(f"UPDATE 下发票 SET {update_sql} WHERE 票号=?", params)

        fate = "部分放量" if iso else "放量"
        域._记命运(
            conn, "下发票", 票号, fate,
            f"{说明}；放量边缘={','.join(released) or '无'}；隔离边缘={','.join(iso) or '无'}",
        )
        conn.commit()
        事务已提交 = True

        row = conn.execute("SELECT * FROM 放量单 WHERE 放量号=?", (放量号,)).fetchone()
        out = 域.序列化放量单(row)
        out.update({k: cert[k] for k in (
            "确认集", "偏差集", "隔离集", "隔离集合", "隔离边缘", "隔离边缘明细",
            "隔离号", "隔离单", "isolation_order",
            "是否可放量", "valid",
            "整票可放量", "策略", "策略码", "问题", "confirmed", "isolated_edges",
        ) if k in cert})
        out["票状态"] = row_status
        out["状态"] = row_status
        out["放量调用成败"] = True
        out["放量成功"] = True
        out["隔离边缘是否非空"] = bool(iso)
        out["隔离边缘非空"] = bool(iso)
        out["隔离非空"] = bool(iso)
        out["幂等"] = False
        return out
    except HTTPException:
        if not 事务已提交:
            conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 装偏差隔离夹具(体: dict) -> dict:
    """装载自带入轨/分桶/下发/两确认一偏差/纠偏回读的完整夹具。"""
    
    from app.services import 入轨, 分桶, 下发, 回读

    报告: dict = {"类型": "偏差隔离", "步骤": []}

    版本们 = 体.get("版本") or []
    if 版本们:
        报告["入轨"] = 入轨.入一批({"批次编号": 体.get("批次编号", ""), "版本": 版本们})

    for bucket in 体.get("分桶") or []:
        报告["步骤"].append({"分桶": 分桶.写桶(bucket)})

    dispatch_results = []
    for item in 体.get("下发") or []:
        dispatch_results.append(下发.下一票(item))
    if dispatch_results:
        报告["下发"] = dispatch_results

    read_results = []
    for item in 体.get("回读") or []:
        read_results.append(回读.记回读(item))
    if read_results:
        报告["回读"] = read_results

    ticket = (
        体.get("票号")
        or (体.get("下发") or [{}])[0].get("票号")
        or (体.get("回读") or [{}])[0].get("票号")
        or (read_results[0].get("票号") if read_results else "")
    )
    if ticket:
        报告["票号"] = ticket
        报告["核证"] = 域.核证(ticket)

    correction_results = []
    if 体.get("执行纠偏") is True:
        for item in 体.get("纠偏回读") or []:
            correction_results.append(回读.记回读(item))
    if correction_results:
        报告["纠偏回读"] = correction_results
        报告["纠偏后核证"] = 域.核证(ticket)
    elif 体.get("纠偏回读"):
        
        报告["待执行纠偏回读"] = 体.get("纠偏回读")

    if 体.get("放量") is True or 体.get("自动放量") is True:
        报告["放量"] = 放量({"票号": ticket, "说明": "夹具自动放量"})

    
    import json
    from app.db import 连接 as 连接2
    from app.services.入轨 import 此刻 as 入轨此刻

    batch_id = 体.get("批次编号") or 域.新号("偏差隔离夹具")
    conn = 连接2()
    try:
        域.确保结构(conn)
        conn.execute(
            "INSERT OR REPLACE INTO 装载批次(编号, 时刻, 报告) VALUES (?,?,?)",
            (batch_id, 入轨此刻(), json.dumps(报告, ensure_ascii=False, default=str)),
        )
        conn.commit()
    finally:
        conn.close()

    报告["批次编号"] = batch_id
    return 报告


release = 放量
create_release = 放量
load_skew_isolation_fixture = 装偏差隔离夹具
