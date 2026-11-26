from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.db import 连接
from app.modules import 偏差隔离升 as 域
from app.services import 放量 as 放量服务

路由 = APIRouter(prefix="/api", tags=["偏差隔离升"])
router = 路由
api_router = 路由


class 放量请求(BaseModel):
    model_config = ConfigDict(extra="allow")

    票号: str = ""
    放量号: str = ""
    说明: str = ""

    def 服务体(self) -> dict[str, Any]:
        data = self.model_dump()
        extra = data.pop("__pydantic_extra__", None)
        if isinstance(extra, dict):
            data.update(extra)
        
        return data


class 核证请求(BaseModel):
    model_config = ConfigDict(extra="allow")

    票号: str = ""

    def 取票号(self) -> str:
        data = self.model_dump()
        return str(
            self.票号
            or data.get("ticket")
            or data.get("ticket_id")
            or data.get("id")
            or ""
        )


def _票号别名(票号: str, ticket: str, ticket_id: str, id: str) -> str:  
    return 票号 or ticket or ticket_id or id


@路由.post("/放量")
@路由.post("/release")
@路由.post("/promote")
@路由.post("/lift")
@路由.post("/skew-isolation/lift")
@路由.post("/偏差隔离升/lift")
@路由.post("/偏差隔离/放量")
@路由.post("/偏差隔离升/放量")
@路由.post("/isolation/release")
@路由.post("/skew-isolation/release")
def 做放量(
    体: Optional[放量请求] = None,
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    id: str = "",  
):
    data = 体.服务体() if 体 is not None else {}
    query_ticket = _票号别名(票号, ticket, ticket_id, id)
    if query_ticket and not data.get("票号") and not data.get("ticket"):
        data["票号"] = query_ticket
    try:
        return 放量服务.放量(data)
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        raise


@路由.get("/certificate")
@路由.get("/skew-isolation")
@路由.get("/skew-isolation/certificate")
@路由.get("/isolation/certificate")
@路由.get("/核证")
@路由.get("/certify")
@路由.get("/certification")
@路由.get("/skew-isolation/certify")
@路由.get("/偏差隔离/核证")
@路由.get("/偏差隔离升/核证")
def 取核证(票号: str = "", ticket: str = "", ticket_id: str = "", id: str = ""):  
    return 域.核证(_票号别名(票号, ticket, ticket_id, id))


@路由.get("/核证/{票号}")
@路由.get("/偏差隔离/核证/{票号}")
@路由.get("/偏差隔离升/核证/{票号}")
def 取核证路径(票号: str):
    return 域.核证(票号)


@路由.get("/tickets/{ticket}/certify")
@路由.get("/tickets/{ticket}/certificate")
@路由.get("/tickets/{ticket}/certification")
@路由.get("/tickets/{ticket}/skew-isolation")
def 取核证英文路径(ticket: str):
    return 域.核证(ticket=ticket)


@路由.post("/tickets/{ticket}/release")
@路由.post("/tickets/{ticket}/promote")
@路由.post("/下发票/{票号}/放量")
@路由.post("/票/{票号}/放量")
def 路径放量(ticket: str = "", 票号: str = ""):
    target = ticket or 票号
    try:
        return 放量服务.放量({"票号": target})
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        raise


@路由.post("/核证")
@路由.post("/偏差隔离/核证")
@路由.post("/偏差隔离升/核证")
def 做核证(
    体: Optional[核证请求] = None,
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    id: str = "",  
):
    target = 体.取票号() if 体 is not None else ""
    return 域.核证(target or _票号别名(票号, ticket, ticket_id, id))


@路由.post("/偏差隔离")
@路由.post("/偏差隔离升")
@路由.post("/isolation")
@路由.post("/isolation/isolate")
@路由.post("/skew-isolation")
@路由.post("/skew-isolation/isolate")
def 做隔离(
    体: Optional[核证请求] = None,
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    id: str = "",  
):
    target = 体.取票号() if 体 is not None else ""
    return 域.隔离偏差(target or _票号别名(票号, ticket, ticket_id, id))


@路由.get("/隔离单")
@路由.get("/隔离集合")
@路由.get("/隔离")
@路由.get("/isolation")
@路由.get("/isolations")
@路由.get("/isolation-set")
@路由.get("/isolation_sets")
@路由.get("/quarantine")
def 列隔离单(票号: str = "", ticket: str = "", ticket_id: str = "", id: str = ""):  
    target = _票号别名(票号, ticket, ticket_id, id)
    conn = 连接()
    try:
        域.确保结构(conn)
        if target:
            rows = conn.execute(
                "SELECT * FROM 隔离单 WHERE 票号=? ORDER BY 更新时 DESC", (target,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM 隔离单 ORDER BY 更新时 DESC LIMIT 200").fetchall()
        return [域.序列化隔离单(r) for r in rows]
    finally:
        conn.close()


@路由.get("/隔离边缘")
@路由.get("/isolation/edges")
@路由.get("/skew-isolation/edges")
@路由.get("/isolation-edges")
@路由.get("/isolation_edges")
@路由.get("/skew-edges")
@路由.get("/skew_edges")
@路由.get("/quarantine/edges")
def 列隔离边缘(
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    id: str = "",  
    全部: bool = False,
    all: bool = False,  
):
    target = _票号别名(票号, ticket, ticket_id, id)
    include_all = 全部 or all
    conn = 连接()
    try:
        域.确保结构(conn)
        sql = "SELECT * FROM 隔离边缘 WHERE 1=1"
        params: list[Any] = []
        if target:
            sql += " AND 票号=?"
            params.append(target)
        if not include_all:
            sql += " AND 状态='隔离中'"
        sql += " ORDER BY 更新时 DESC LIMIT 200"
        return [域.序列化隔离边缘(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


@路由.get("/偏差证")
@路由.get("/deviations")
@路由.get("/skew-certificates")
def 列偏差证(票号: str = "", ticket: str = "", ticket_id: str = ""):
    target = 票号 or ticket or ticket_id
    conn = 连接()
    try:
        域.确保结构(conn)
        if target:
            rows = conn.execute(
                "SELECT * FROM 偏差证 WHERE 票号=? ORDER BY 最近时 DESC", (target,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM 偏差证 ORDER BY 最近时 DESC LIMIT 200").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/放量单")
@路由.get("/releases")
@路由.get("/release-orders")
def 列放量单(票号: str = "", ticket: str = "", ticket_id: str = "", id: str = ""):  
    target = _票号别名(票号, ticket, ticket_id, id)
    conn = 连接()
    try:
        域.确保结构(conn)
        if target:
            rows = conn.execute(
                "SELECT * FROM 放量单 WHERE 票号=? ORDER BY rowid DESC", (target,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM 放量单 ORDER BY rowid DESC LIMIT 200").fetchall()
        return [域.序列化放量单(r) for r in rows]
    finally:
        conn.close()
