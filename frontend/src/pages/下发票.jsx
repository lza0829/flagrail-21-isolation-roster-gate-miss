import React, { useEffect, useState } from "react";
import { get, postFixture } from "../api.js";

export default function 下发票() {
  const [rows, setRows] = useState([]);
  const [讯, set讯] = useState("");
  const 刷 = async () => setRows(await get("/下发票"));
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);
  return (
    <div>
      <h1 className="题">下发票</h1>
      <p className="述">版本对分桶的一次灰度下发。票号幂等；偏差会同票生成隔离集合，放量后票态可为「部分放量」。</p>
      <div className="行">
        <button onClick={async () => { await postFixture("下发样例"); await 刷(); set讯("已灌下发样例"); }}>灌下发样例</button>
        <button className="次" onClick={() => 刷()}>刷新</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {!rows.length ? <div className="空态">尚无下发票（需先入轨+分桶）</div> : (
        <table>
          <thead><tr><th>票号</th><th>版本键</th><th>桶键</th><th>状态</th><th>隔离边缘</th><th>下发时</th></tr></thead>
          <tbody>{rows.map((r) => {
            const iso = Array.isArray(r.隔离集合) ? r.隔离集合 : [];
            const tone = r.状态 === "已回滚" || r.状态 === "已失效" ? "败" : r.状态 === "部分放量" || r.状态 === "隔离中" ? "警" : "通";
            return (
              <tr key={r.票号}>
                <td>{r.票号}</td><td>{r.版本键}</td><td>{r.桶键}</td>
                <td><span className={`徽章 ${tone}`}>{r.状态}</span></td>
                <td>{iso.length ? iso.join(", ") : "—"}</td>
                <td>{r.下发时}</td>
              </tr>
            );
          })}</tbody>
        </table>
      )}
    </div>
  );
}
