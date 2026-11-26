
"""偏差隔离升断言脚本。

用临时 SQLite 库装载「两确认一偏差」夹具，断言：
1. 所见版本拧花的“确认”会被改判偏差，放量门不得吞偏差；
2. 偏差证、隔离集合、票态与放量结果同票一致；
3. 本仓钉死「隔离放行其余」：放量调用成功且隔离边缘非空必须可同时区分；
4. 纠偏后再次放量，隔离清空且票态转为已放量。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

_TMP_DATA = Path(tempfile.mkdtemp(prefix="flagrail-skew-assert-"))
os.environ["数据目录"] = str(_TMP_DATA)
os.environ["夹具目录"] = str(ROOT / "fixtures")

from app.modules import 偏差隔离升 as 域  
from app.seed import 初始化库  
from app.services import 放量, 回读  

初始化库()


def 断言(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  ✓ {message}")


def main() -> int:
    fixture_path = ROOT / "fixtures" / "偏差隔离样例.json"
    body = json.loads(fixture_path.read_text(encoding="utf-8"))
    report = 放量.装偏差隔离夹具(body)
    ticket = report["票号"]

    print("[1/4] 两确认一偏差不得被吞成全确认")
    cert = report["核证"]
    断言(cert["确认集"] == ["edge-a", "edge-b"], f"确认集应为 a/b，实际 {cert['确认集']}")
    断言(cert["偏差集"] == ["edge-c"], f"偏差集应为 c，实际 {cert['偏差集']}")
    断言(cert["隔离集"] == ["edge-c"], f"隔离集必须列出 c，实际 {cert['隔离集']}")
    断言(cert["valid"] is True, "核证账目 valid 应为 true")
    断言(cert["整票可放量"] is False, "存在偏差时整票诊断位应为 false")

    print("[2/4] 放量调用成败与隔离非空必须是两个可区分维度")
    released = 放量.放量({"票号": ticket, "说明": "偏差脚本首次放量"})
    断言(released["放量调用成败"] is True, "隔离放行口径下，确认边缘存在时放量调用应成功")
    断言(released["隔离边缘是否非空"] is True, "放量成功的同时必须明确返回隔离边缘非空")
    断言(released["状态"] == "部分放量", f"票态应为部分放量，实际 {released['状态']}")
    断言(released["放量集"] == ["edge-a", "edge-b"], "只有确认边缘可进入放量集")
    断言("edge-c" not in released["放量集"], "偏差边缘 edge-c 不得被放量")

    print("[3/4] 回读台使用的隔离实体必须非空")
    conn = 域.连接()
    try:
        rows = conn.execute(
            "SELECT 边缘键 FROM 隔离边缘 WHERE 票号=? AND 状态='隔离中'", (ticket,)
        ).fetchall()
        edges = [r["边缘键"] for r in rows]
    finally:
        conn.close()
    断言(edges == ["edge-c"], f"隔离边缘表应列出 edge-c，实际 {edges}")

    print("[4/4] 纠偏后再放量应清空隔离并全量已放量")
    corrected = 回读.记回读(body["纠偏回读"][0])
    断言(corrected["隔离边缘是否非空"] is False, "纠偏回读后活动隔离集合应为空")
    cert2 = 域.核证(ticket)
    断言(cert2["偏差集"] == [] and cert2["隔离集"] == [], "纠偏后偏差集/隔离集均应为空")

    released2 = 放量.放量({"票号": ticket, "说明": "偏差脚本纠偏后放量"})
    断言(released2["放量调用成败"] is True, "纠偏后放量应成功")
    断言(released2["隔离边缘是否非空"] is False, "纠偏后隔离边缘应为空")
    断言(released2["状态"] == "已放量", f"票态应为已放量，实际 {released2['状态']}")
    断言(released2["放量集"] == ["edge-a", "edge-b", "edge-c"], "三个边缘均应进入放量集")

    print("\n偏差隔离断言全部通过：放量门没有吞偏差。")
    print(f"临时库：{_TMP_DATA / '灰度轨.db'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\n偏差隔离断言失败：{exc}", file=sys.stderr)
        raise
