import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.db import 当前夹具目录, 连接
from app.modules import 偏差隔离升 as 偏差域
from app.services import 入轨, 分桶, 下发, 回读, 命运, 贯验, 目录, 放量

路由 = APIRouter(prefix="/api")
router = 路由
api_router = 路由


class 入轨请求(BaseModel):
    批次编号: str = ""
    版本: list = Field(default_factory=list)


class 分桶请求(BaseModel):
    桶键: str
    开关键: str
    桶类型: str = "百分比"
    规则: dict = Field(default_factory=dict)
    状态: str = "生效"


class 下发请求(BaseModel):
    票号: str = ""
    版本键: str
    桶键: str
    说明: str = ""


class 回读请求(BaseModel):
    model_config = ConfigDict(extra="allow")

    证号: str = ""
    票号: str = ""
    边缘键: str = ""
    所见版本键: str = ""
    结果: str = "确认"
    说明: str = ""

    def 服务体(self) -> dict:
        
        
        return self.model_dump(exclude_unset=True)


class 回滚请求(BaseModel):
    票号: str
    说明: str = ""


class 失效请求(BaseModel):
    版本键: str
    说明: str = ""


class 放量请求(BaseModel):
    票号: str = ""
    放量号: str = ""
    说明: str = ""

    model_config = ConfigDict(extra="allow")


@路由.get("/健康")
def 健康():
    return {
        "正常": True,
        "项目": "灰度轨",
        "领域": "基础设施",
        "子方向": "中间件",
        "骨架": "开关版本入轨→分桶灰度下发→回读确认→失效/回滚互证",
    }


@路由.get("/总览")
def 取总览():
    return 目录.总览()


@路由.get("/站规")
def 站规():
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
    finally:
        conn.close()


@路由.get("/开关版本")
def 列版本(状态: str = ""):
    conn = 连接()
    try:
        if 状态:
            rows = conn.execute(
                "SELECT * FROM 开关版本 WHERE 状态=? ORDER BY 入轨时 DESC", (状态,)
            )
        else:
            rows = conn.execute("SELECT * FROM 开关版本 ORDER BY 入轨时 DESC")
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["载荷"] = json.loads(d["载荷"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/分桶规")
def 列分桶():
    conn = 连接()
    try:
        out = []
        for r in conn.execute("SELECT * FROM 分桶规 ORDER BY 更新时 DESC"):
            d = dict(r)
            try:
                d["规则"] = json.loads(d["规则"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/下发票")
def 列下发(状态: str = ""):
    conn = 连接()
    try:
        if 状态:
            rows = conn.execute(
                "SELECT * FROM 下发票 WHERE 状态=? ORDER BY 下发时 DESC", (状态,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM 下发票 ORDER BY 下发时 DESC").fetchall()
        out = []
        json_fields = ("隔离集合", "放量集", "最近核证")
        for r in rows:
            d = dict(r)
            for key in json_fields:
                if key in d:
                    try:
                        default = {} if key == "最近核证" else []
                        d[key] = json.loads(d[key]) if d[key] else default
                    except Exception:
                        pass
            d["status"] = d.get("状态", "")
            d["ticket"] = d.get("票号", "")
            d["ticket_id"] = d.get("票号", "")
            if "隔离集合" in d:
                d["isolation_set"] = d["隔离集合"]
                d["has_isolation"] = bool(d["隔离集合"])
            if "放量集" in d:
                d["release_set"] = d["放量集"]
                d["released_edges"] = d["放量集"]
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/回读证")
def 列回读():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 回读证 ORDER BY 回读时 DESC LIMIT 200")]
    finally:
        conn.close()


@路由.get("/命运账")
def 列命运():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 命运账 ORDER BY 编号 DESC LIMIT 100")]
    finally:
        conn.close()


@路由.get("/批次")
def 列批次():
    conn = 连接()
    try:
        out = []
        for r in conn.execute("SELECT * FROM 装载批次 ORDER BY 时刻 DESC LIMIT 30"):
            d = dict(r)
            try:
                d["报告"] = json.loads(d["报告"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/空桩")
def 列空桩():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 空桩 ORDER BY 名")]
    finally:
        conn.close()


@路由.post("/入轨")
def 做入轨(体: 入轨请求):
    return 入轨.入一批(体.model_dump())


@路由.post("/分桶")
def 做分桶(体: 分桶请求):
    return 分桶.写桶(体.model_dump())


@路由.post("/下发")
def 做下发(体: 下发请求):
    return 下发.下一票(体.model_dump())


@路由.post("/回读")
@路由.post("/回读证")
@路由.post("/readback")
@路由.post("/readbacks")
def 做回读(
    体: 回读请求 | None = None,
    票号: str = "",
    ticket: str = "",
    边缘键: str = "",
    edge: str = "",
):
    data = 体.服务体() if 体 is not None else {}
    query_ticket = 票号 or ticket
    query_edge = 边缘键 or edge
    if query_ticket and not data.get("票号") and not data.get("ticket"):
        data["票号"] = query_ticket
    if query_edge and not data.get("边缘键") and not data.get("edge"):
        data["边缘键"] = query_edge
    return 回读.记回读(data)


@路由.post("/回滚")
def 做回滚(体: 回滚请求):
    return 命运.回滚票(体.model_dump())


@路由.post("/失效")
def 做失效(体: 失效请求):
    return 命运.失效版本(体.model_dump())


@路由.post("/放量")
def 核心放量(
    体: 放量请求 | None = None,
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    id: str = "",  
):
    data = 体.model_dump() if 体 is not None else {}
    query_ticket = 票号 or ticket or ticket_id or id
    if query_ticket and not data.get("票号") and not data.get("ticket"):
        data["票号"] = query_ticket
    try:
        return 放量.放量(data)
    except HTTPException as exc:
        
        
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        raise


@路由.get("/核证")
def 核心核证(票号: str = "", ticket: str = "", ticket_id: str = "", id: str = ""):  
    return 偏差域.核证(票号 or ticket or ticket_id or id)


@路由.get("/隔离边缘")
def 核心隔离边缘(
    票号: str = "",
    ticket: str = "",
    ticket_id: str = "",
    全部: bool = False,
    all: bool = False,  
):
    target = 票号 or ticket or ticket_id
    include_all = 全部 or all
    conn = 连接()
    try:
        偏差域.确保结构(conn)
        sql = "SELECT * FROM 隔离边缘 WHERE 1=1"
        params: list = []
        if target:
            sql += " AND 票号=?"
            params.append(target)
        if not include_all:
            sql += " AND 状态='隔离中'"
        sql += " ORDER BY 更新时 DESC LIMIT 200"
        return [偏差域.序列化隔离边缘(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


@路由.get("/隔离集合")
@路由.get("/隔离单")
def 核心隔离集合(票号: str = "", ticket: str = "", ticket_id: str = ""):
    target = 票号 or ticket or ticket_id
    conn = 连接()
    try:
        偏差域.确保结构(conn)
        if target:
            rows = conn.execute(
                "SELECT * FROM 隔离单 WHERE 票号=? ORDER BY 更新时 DESC", (target,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM 隔离单 ORDER BY 更新时 DESC LIMIT 200").fetchall()
        return [偏差域.序列化隔离单(r) for r in rows]
    finally:
        conn.close()


@路由.get("/放量单")
def 核心放量单(票号: str = "", ticket: str = "", ticket_id: str = ""):
    target = 票号 or ticket or ticket_id
    conn = 连接()
    try:
        偏差域.确保结构(conn)
        rows = conn.execute(
            "SELECT * FROM 放量单 WHERE (?='' OR 票号=?) ORDER BY rowid DESC LIMIT 200",
            (target, target),
        ).fetchall()
        return [偏差域.序列化放量单(r) for r in rows]
    finally:
        conn.close()


def _分发夹具(体: dict):
    类型 = 体.get("类型") or 体.get("type") or 体.get("fixture_type") or "入轨"
    类型文本 = str(类型)
    if 类型文本 in ("偏差隔离", "偏差隔离升", "偏差隔离样例", "skew-isolation", "skew_isolation"):
        return 放量.装偏差隔离夹具(体)
    if 类型文本 == "入轨":
        return 入轨.入一批(体)
    if 类型文本 == "分桶":
        outs = [分桶.写桶(x) for x in 体.get("分桶") or []]
        return {"类型": "分桶", "结果": outs}
    if 类型文本 == "下发":
        return 下发.装下发夹具(体)
    if 类型文本 == "回读":
        return 回读.装回读夹具(体)
    if 类型文本 == "放量":
        return 放量.放量(体.get("放量") if isinstance(体.get("放量"), dict) else 体)
    if 类型文本 == "回滚":
        return 命运.回滚票(体)
    raise HTTPException(400, f"未知夹具类型:{类型}")


@路由.post("/装载/夹具")
@路由.post("/fixtures/load")
@路由.post("/fixture/load")
@路由.post("/load-fixture")
def 装夹具(
    名: str = "",
    name: str = "",
    fixture: str = "",
    fixture_name: str = "",
    体: dict | None = None,
):
    data = 体 if isinstance(体, dict) else {}
    目标 = (
        名 or name or fixture or fixture_name
        or data.get("名") or data.get("name")
        or data.get("夹具名") or data.get("fixture_name") or data.get("fixture")
        or ""
    )

    
    夹具内容键 = ("类型", "type", "版本", "分桶", "下发", "回读", "纠偏回读")
    if any(k in data for k in 夹具内容键):
        return _分发夹具(data)

    目标 = str(目标 or "入轨样例")
    别名 = {
        "偏差隔离升": "偏差隔离样例",
        "偏差隔离": "偏差隔离样例",
        "skew-isolation-sample": "skew-isolation-sample",
        "skew-isolation": "偏差隔离样例",
        "skew_isolation": "偏差隔离样例",
    }
    文件名 = 别名.get(目标, 目标)
    路径 = 当前夹具目录() / f"{文件名}.json"
    if not 路径.exists() and 文件名 != 目标:
        路径 = 当前夹具目录() / f"{目标}.json"
    if not 路径.exists():
        raise HTTPException(404, f"夹具不存在:{目标}")
    file_body = json.loads(路径.read_text(encoding="utf-8"))
    return _分发夹具(file_body)


@路由.post("/贯验")
def 做贯验():
    return 贯验.跑贯验()


@路由.get("/贯验")
def 列贯验():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 轨贯验 ORDER BY 编号 DESC LIMIT 20")]
    finally:
        conn.close()

from app.modules import 隔离名册闸 as _bf_mod_21


@路由.get("/核证/隔离名册")
def 取核证_21(键: str | None = None):
    conn = 连接()
    try:
        return _bf_mod_21.查现场(conn, 键)
    finally:
        conn.close()


@路由.post("/核证/隔离名册/巡检")
def 巡检核证_21(payload: dict | None = None):
    return _bf_mod_21.巡检包(payload or {})

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

