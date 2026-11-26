import React, { useEffect, useMemo, useState } from "react";
import { get, post, postFixture } from "../api.js";

function 集签({ title, rows, tone }) {
  return (
    <div className={`隔离集卡 ${tone || ""}`}>
      <b>{title}</b>
      <div className="签行">
        {!rows?.length ? <span className="空签">∅</span> : rows.map((x) => (
          <span key={x} className={`徽章 ${tone === "败" ? "败" : tone === "警" ? "警" : "通"}`}>{x}</span>
        ))}
      </div>
    </div>
  );
}

export default function 回读台() {
  const [rows, setRows] = useState([]);
  const [isoRows, setIsoRows] = useState([]);
  const [ticket, setTicket] = useState("");
  const [cert, setCert] = useState(null);
  const [release, setRelease] = useState(null);
  const [讯, set讯] = useState("");

  const 刷 = async () => {
    const [readbacks, isolations] = await Promise.all([
      get("/回读证"),
      get("/隔离边缘?全部=true"),
    ]);
    setRows(readbacks);
    setIsoRows(isolations);
    setTicket((old) => old || readbacks[0]?.票号 || "");
  };

  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  useEffect(() => {
    if (!ticket) return;
    get(`/核证?票号=${encodeURIComponent(ticket)}`)
      .then(setCert)
      .catch(() => setCert(null));
  }, [ticket, rows]);

  const activeIso = useMemo(() => isoRows.filter((x) => x.状态 === "隔离中"), [isoRows]);

  const 灌偏差夹具 = async () => {
    set讯("RUNNING…");
    try {
      const report = await postFixture("偏差隔离样例");
      const t = report.票号 || "票-skew-isolation";
      setTicket(t);
      await 刷();
      setCert(await get(`/核证?票号=${encodeURIComponent(t)}`));
      set讯("已灌两确认一偏差；偏差边缘必须出现在隔离集合");
    } catch (e) {
      set讯(String(e));
    }
  };

  const 跑核证 = async () => {
    set讯("RUNNING…");
    try {
      const c = await get(`/核证?票号=${encodeURIComponent(ticket)}`);
      setCert(c);
      set讯(c.valid ? "核证账目 valid" : `核证异常：${(c.问题 || []).join("；")}`);
    } catch (e) { set讯(String(e)); }
  };

  const 跑放量 = async () => {
    set讯("RUNNING…");
    try {
      const r = await post("/放量", { 票号: ticket });
      setRelease(r);
      setCert(r.核证 || r);
      await 刷();
      set讯(r.隔离边缘是否非空 ? "放量调用成功；确认边缘放量，隔离边缘非空" : "放量调用成功；隔离边缘为空");
    } catch (e) {
      set讯(`放量调用失败：${e.message}`);
      await 刷().catch(() => {});
    }
  };

  return (
    <div>
      <h1 className="题">回读台</h1>
      <p className="述">
        边缘对下发票的确认。所见版本与票面不一致 → 记「偏差」，并同票落入隔离集合；
        本仓放量口径钉死为「隔离放行其余」，不允许吞偏差当全确认。
      </p>
      <div className="行">
        <button onClick={灌偏差夹具}>灌两确认一偏差夹具</button>
        <button onClick={async () => { await postFixture("回读样例"); await 刷(); set讯("已灌回读样例"); }}>灌回读样例</button>
        <button className="次" onClick={() => 刷().catch((e) => set讯(String(e)))}>刷新</button>
      </div>

      <div className="行" style={{ alignItems: "end", gap: 12, marginTop: 16 }}>
        <label>
          核证票号
          <input value={ticket} onChange={(e) => setTicket(e.target.value)} placeholder="票号" style={{ marginLeft: 8, minWidth: 280 }} />
        </label>
        <button className="次" onClick={跑核证} disabled={!ticket}>核证</button>
        <button className="信" onClick={跑放量} disabled={!ticket}>隔离放行其余 / 放量</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}

      {cert && (
        <section className="卡" style={{ margin: "16px 0", padding: 16, border: "1px solid var(--线, #2a3140)", borderRadius: 12 }}>
          <div className="行" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>核证 · {cert.票号}</h2>
            <span className={`徽章 ${cert.valid ? "通" : "败"}`}>valid={String(cert.valid)}</span>
          </div>
          <p className="述" style={{ margin: "8px 0 12px" }}>
            策略：{cert.策略} · 票态：{cert.票状态} · 可放量：{String(cert.是否可放量)} · 整票可放量：{String(cert.整票可放量)}
          </p>
          <div className="网格" style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12 }}>
            <集签 title="确认集" rows={cert.确认集} tone="通" />
            <集签 title="偏差集" rows={cert.偏差集} tone="警" />
            <集签 title="隔离集（核证必列）" rows={cert.隔离集} tone="败" />
          </div>
          {!!(cert.问题 || []).length && <p className="讯">问题：{cert.问题.join("；")}</p>}
        </section>
      )}

      {release && (
        <p className="讯">
          最近放量：{release.放量号} · 成败={String(release.放量调用成败)} ·
          状态={release.状态} · 隔离边缘非空={String(release.隔离边缘是否非空)}
        </p>
      )}

      <h2 className="题" style={{ fontSize: 20, marginTop: 24 }}>隔离边缘</h2>
      {!isoRows.length ? <div className="空态">尚无隔离边缘；偏差回读落库后必须出现在这里</div> : (
        <table>
          <thead><tr><th>票号</th><th>边缘</th><th>偏差证</th><th>所见版本</th><th>目标版本</th><th>状态</th><th>更新时</th></tr></thead>
          <tbody>{isoRows.map((r) => (
            <tr key={`${r.票号}-${r.边缘键}`} data-active={r.状态 === "隔离中"}>
              <td>{r.票号}</td>
              <td><b>{r.边缘键}</b></td>
              <td>{r.偏差证号}</td>
              <td>{r.所见版本键}</td>
              <td>{r.目标版本键}</td>
              <td><span className={"徽章 " + (r.状态 === "隔离中" ? "败" : "通")}>{r.状态}</span></td>
              <td>{r.更新时}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <p className="述">当前隔离中：{activeIso.length} 条。纠偏回读会把对应边缘标记为「已纠偏」。</p>

      <h2 className="题" style={{ fontSize: 20, marginTop: 24 }}>回读证</h2>
      {!rows.length ? <div className="空态">尚无回读证</div> : (
        <table>
          <thead><tr><th>证号</th><th>票号</th><th>边缘</th><th>所见版本</th><th>结果</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.证号} data-skew={r.结果 === "偏差" ? "1" : "0"}>
              <td>{r.证号}</td><td>{r.票号}</td><td>{r.边缘键}</td>
              <td>{r.所见版本键}</td>
              <td><span className={"徽章 " + (r.结果 === "确认" ? "通" : "败")}>{r.结果}</span></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
