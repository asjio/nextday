import { useEffect, useRef } from "react";
import * as echarts from "echarts";

// 胜率曲线图 -- 账本风格(ECharts)
export default function WinrateChart({ records }) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current);
    }
    const chart = chartRef.current;
    const dates = records.map((r) => r.target_date.slice(5));
    const mk = (r) => r === null || r === undefined ? null : +(r * 100).toFixed(1);
    const option = {
      backgroundColor: "transparent",
      grid: { left: 46, right: 20, top: 46, bottom: 24 },
      legend: {
        top: 8,
        textStyle: { color: "#5c554a", fontSize: 12 },
        itemWidth: 14,
        data: ["全体", "Top12", "高置信P>=70%", "基准49.2%"],
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#26221c",
        borderColor: "#26221c",
        textStyle: { color: "#f6f1e7", fontSize: 12 },
        valueFormatter: (v) => (v === null ? "无数据" : v + "%"),
      },
      xAxis: {
        type: "category",
        data: dates,
        axisLine: { lineStyle: { color: "#d8cdb8" } },
        axisLabel: { color: "#5c554a", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        name: "命中率 %",
        nameTextStyle: { color: "#9a9184", fontSize: 11 },
        splitLine: { lineStyle: { color: "#e8dfcc" } },
        axisLabel: { color: "#9a9184", fontSize: 11 },
      },
      series: [
        {
          name: "全体",
          type: "line",
          data: records.map((r) => mk(r.hit_rate)),
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { color: "#d98e3f", width: 2.5 },
          itemStyle: { color: "#d98e3f" },
          label: { show: true, fontSize: 10, color: "#d98e3f", formatter: "{c}" },
        },
        {
          name: "Top12",
          type: "line",
          data: records.map((r) => mk(r.top12_hit_rate)),
          symbol: "rect",
          symbolSize: 8,
          lineStyle: { color: "#b02a2a", width: 2.5 },
          itemStyle: { color: "#b02a2a" },
          label: { show: true, fontSize: 10, color: "#b02a2a", formatter: "{c}" },
        },
        {
          name: "高置信P>=70%",
          type: "line",
          data: records.map((r) => mk(r.high_conf_hit_rate)),
          symbol: "triangle",
          symbolSize: 9,
          lineStyle: { color: "#a8321e", width: 2.5 },
          itemStyle: { color: "#a8321e" },
          label: { show: true, fontSize: 10, color: "#a8321e", formatter: "{c}" },
        },
        {
          name: "基准49.2%",
          type: "line",
          data: records.map(() => 49.2),
          symbol: "none",
          lineStyle: { color: "#9a9184", type: "dashed", width: 1.5 },
          itemStyle: { color: "#9a9184" },
        },
      ],
    };
    chart.setOption(option, true);
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [records]);

  return <div ref={ref} style={{ width: "100%", height: 320 }} />;
}
