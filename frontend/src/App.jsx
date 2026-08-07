import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import WinrateChart from "./WinrateChart.jsx";

const fmtPct = (v, signed = false) => {
  if (v === null || v === undefined) return "--";
  const s = signed && v > 0 ? "+" : "";
  return s + Number(v).toFixed(2) + "%";
};

// ---------- tooltip提示 ----------
function Tip({ text, children }) {
  const [show, setShow] = useState(false);
  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <span className="absolute left-0 bottom-full mb-1 z-50 bg-ink text-white text-[11px] leading-tight px-2.5 py-1.5 rounded-md shadow-lg whitespace-normal w-48">
          {text}
        </span>
      )}
    </span>
  );
}

// ---------- 顶部累计统计 ----------
function StatBoard({ overview }) {
  const { days, total_n, summary } = overview;
  const cells = [
    {
      label: "累计验证交易日",
      tip: "已有对账结果的交易日数量",
      value: days,
      unit: "天",
    },
    {
      label: "累计样本",
      tip: "所有交易日中候选股的总数",
      value: total_n,
      unit: "个",
    },
    {
      label: "全体命中率",
      tip: "全部候选股(约200只)次日实际上涨的比例",
      value: summary.hit_rate_all,
      unit: "%",
      good: true,
    },
    {
      label: "Top12命中率",
      tip: "综合上涨概率、大跌风险、稳定性评分后排名前12的股票，其次日实际上涨比例",
      value: summary.hit_rate_top12,
      unit: "%",
      good: true,
    },
    {
      label: "高置信命中率",
      tip: "模型预测上涨概率>=70%的股票中，次日实际上涨的比例",
      value: summary.hit_rate_high_conf ?? "--",
      unit: summary.hit_rate_high_conf != null ? "%" : "",
      good: true,
    },
    {
      label: "平均次日收益",
      tip: "全部候选股次日实际平均涨跌幅",
      value: fmtPct(summary.avg_actual, true),
      unit: "",
      good: summary.avg_actual >= 0,
    },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cells.map((c) => (
        <div key={c.label} className="bg-card border border-line rounded-lg px-4 py-3">
          <div className="text-[11px] text-ink-faint mb-1">
            <Tip text={c.tip}>
              <span className="cursor-help border-b border-dashed border-ink-faint/50">{c.label}</span>
            </Tip>
          </div>
          <div className={`font-num text-xl font-semibold ${c.good ? "text-rise" : "text-ink"}`}>
            {c.value}
            <span className="text-xs text-ink-faint ml-1 font-normal">{c.unit}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------- 台账表格 ----------
function LedgerTable({ pred }) {
  const cols = [
    ["序", "w-10", "排序序号"],
    ["代码", "w-20", "股票代码"],
    ["名称", "w-28", "股票名称"],
    ["明日上涨概率", "w-56", "模型预测次日上涨的概率，数值越高越看好"],
    ["P涨>5%", "w-20", "历史相似日中次日涨幅超过5%的比例，高表示大涨概率大"],
    ["P大跌>5%", "w-20", "历史相似日中次日跌幅超过5%的比例，高表示风险大"],
    ["次日中位", "w-24", "历史相似日次日收益的中位数"],
    ["今日涨幅", "w-24", "当天实际涨跌幅"],
  ];
  if (pred.validated) {
    cols.push(["实际涨跌", "w-24", "对账后的实际涨跌幅"]);
    cols.push(["对账", "w-16", "是否命中预测"]);
  }
  return (
    <div className="bg-card border border-line rounded-lg overflow-hidden">
      <div className="max-h-[520px] overflow-y-auto">
        <table className="w-full text-[13px]">
          <thead className="sticky top-0 bg-paper z-10">
            <tr className="border-b border-line text-ink-soft">
              {cols.map(([h, w, tip]) => (
                <th key={h} className={`px-3 py-2.5 text-left font-medium text-xs ${w}`}>
                  <Tip text={tip}>
                    <span className="cursor-help border-b border-dashed border-ink-faint/50">{h}</span>
                  </Tip>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pred.items.map((it, i) => {
              const hitCls =
                it.hit === null || it.hit === undefined
                  ? ""
                  : it.hit
                  ? "text-rise"
                  : "text-fall";
              return (
                <tr key={it.code} className="ledger-row border-b border-line/60 last:border-0">
                  <td className="px-3 py-2 text-ink-faint font-num">{String(i + 1).padStart(2, "0")}</td>
                  <td className="px-3 py-2 font-num">{it.code}</td>
                  <td className="px-3 py-2">{it.name}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="pbar flex-1">
                        <div style={{ width: `${it.p_up}%` }} />
                      </div>
                      <span className="font-num text-rise w-12 text-right">{it.p_up}%</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-num text-ink-soft">{it.p_up5 != null ? it.p_up5 + "%" : "--"}</td>
                  <td className="px-3 py-2 font-num text-fall">{it.p_down5}%</td>
                  <td className="px-3 py-2 font-num">{fmtPct(it.median, true)}</td>
                  <td className="px-3 py-2 font-num">{fmtPct(it.r1, true)}</td>
                  {pred.validated && (
                    <>
                      <td className={`px-3 py-2 font-num ${hitCls}`}>{fmtPct(it.actual, true)}</td>
                      <td className="px-3 py-2">
                        {it.hit === null || it.hit === undefined ? (
                          <span className="text-ink-faint text-xs">未对账</span>
                        ) : it.hit ? (
                          <span className="tag-hit">命中</span>
                        ) : (
                          <span className="tag-miss">失误</span>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- 执行日志 ----------
function RunPanel({ onDone }) {
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);

  const poll = useCallback(() => {
    api.runStatus().then((s) => {
      setStatus(s);
      if (s.running) {
        setTimeout(poll, 1500);
      } else {
        setRunning(false);
        if (onDone) onDone();
      }
    });
  }, [onDone]);

  const run = async () => {
    setRunning(true);
    await api.run();
    setTimeout(poll, 1000);
  };

  return (
    <div className="bg-card border border-line rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-ink-soft">手动执行每日流程</span>
        <button
          onClick={run}
          disabled={running}
          className="px-4 py-1.5 text-sm bg-accent text-white rounded-md hover:opacity-90"
        >
          {running ? "执行中..." : "立即执行"}
        </button>
      </div>
      {status && (
        <div className="text-[11px] leading-5 text-ink-soft max-h-36 overflow-y-auto whitespace-pre-wrap font-num">
          {status.log.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
          {status.error && <div className="text-rise mt-1">{status.error}</div>}
          {status.last_done && !status.error && (
            <div className="text-fall mt-1">上次完成: {status.last_done}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------- 主组件 ----------
export default function App() {
  const [overview, setOverview] = useState(null);
  const [winrate, setWinrate] = useState(null);
  const [dates, setDates] = useState([]);
  const [validated, setValidated] = useState({});
  const [curDate, setCurDate] = useState(null);
  const [pred, setPred] = useState(null);
  const [err, setErr] = useState("");

  const loadAll = useCallback(() => {
    api.overview().then(setOverview).catch((e) => setErr(String(e)));
    api.winrate().then(setWinrate);
    api.dates().then((d) => {
      setDates(d.dates);
      setValidated(d.validated);
      setCurDate((cur) => cur || d.dates[0] || null);
    });
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!curDate) return;
    setPred(null);
    api.predictions(curDate).then(setPred).catch((e) => setErr(String(e)));
  }, [curDate]);

  if (err) {
    return (
      <div className="max-w-5xl mx-auto p-8 text-rise">
        加载失败: {err}
        <button className="ml-4 underline" onClick={() => { setErr(""); loadAll(); }}>
          重试
        </button>
      </div>
    );
  }
  if (!overview || !winrate) {
    return <div className="max-w-5xl mx-auto p-8 text-ink-faint">加载中...</div>;
  }

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* 页头 */}
      <header className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-ink">NextDay 次日方向台账</h1>
        <p className="text-ink-faint text-xs mt-1">
          历史相似日概率模型 · 逐日实测对账 · 随机基准 49.2%
        </p>
      </header>

      {/* 累计统计 */}
      <StatBoard overview={overview} />

      {/* 胜率曲线 */}
      <section className="mt-6 bg-card border border-line rounded-lg p-4">
        <div className="flex items-baseline justify-between mb-1">
          <h2 className="text-sm font-medium text-ink">胜率曲线</h2>
          <span className="text-[11px] text-ink-faint">每预测日收盘后, 用真实次日涨跌对账</span>
        </div>
        {winrate.records.length ? (
          <WinrateChart records={winrate.records} />
        ) : (
          <div className="text-ink-faint text-sm py-8 text-center">尚无对账记录, 首个交易日收盘后生成</div>
        )}
      </section>

      {/* 预测台账 */}
      <section className="mt-6">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
          <h2 className="text-sm font-medium text-ink">预测台账</h2>
          <div className="flex gap-2 flex-wrap">
            {dates.map((d) => (
              <button
                key={d}
                onClick={() => setCurDate(d)}
                className={`px-3 py-1.5 text-xs rounded-md border font-num transition-colors ${
                  d === curDate
                    ? "bg-ink text-white border-ink"
                    : "bg-card text-ink-soft border-line hover:border-ink-faint"
                }`}
              >
                {d}
                {validated[d] ? " ·已对账" : ""}
              </button>
            ))}
          </div>
        </div>

        {pred && (
          <>
            <div className="text-xs text-ink-soft mb-2 font-num flex items-center gap-4 flex-wrap">
              <Tip text="模型以这天收盘数据为基准运行">
                <span className="cursor-help border-b border-dashed border-ink-faint/50">数据基准日</span>
              </Tip>{" "}
              <b className="text-ink">{pred.date}</b>
              <Tip text="模型预测的是这天的涨跌，通常是下一个交易日">
                <span className="cursor-help border-b border-dashed border-ink-faint/50">预测目标日</span>
              </Tip>{" "}
              <b className="text-accent">{pred.target_date || "待定"}</b>
              {pred.target_date > today && <span className="text-ink-faint ml-1">(未到)</span>}
              <Tip text="用于找相似形态的历史交易日数量，越大越可靠">
                <span className="cursor-help border-b border-dashed border-ink-faint/50">历史相似日样本</span>
              </Tip>{" "}
              {pred.n_samples}
              <Tip text="全市场随机买一只次日涨的概率，模型命中率需高于此才有价值">
                <span className="cursor-help border-b border-dashed border-ink-faint/50">随机基准</span>
              </Tip>{" "}
              {fmtPct(pred.baseline * 100)}
              {pred.validated ? (
                <span className="tag-hit">已对账</span>
              ) : (
                <span className="text-ink-faint">待目标日收盘后对账</span>
              )}
            </div>
            <LedgerTable pred={pred} />
          </>
        )}
      </section>

      {/* 手动执行 */}
      <section className="mt-6 mb-4">
        <RunPanel onDone={loadAll} />
      </section>

      <footer className="text-center text-[11px] text-ink-faint py-4">
        概率预测非投资建议 · 模型保质期仅一个交易日 · 数据源: 腾讯财经
      </footer>
    </div>
  );
}
