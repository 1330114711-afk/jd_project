"""
run_pipeline.py — 一键流水线：从 raw 到 report

作用
    按依赖顺序串联全部步骤，单命令复现整个项目。
    逐步记录耗时 / 退出码 / 产出文件，任一步失败即中断并给出定位提示。

流水线阶段
    S1  数据体检        src/01_data_health_check.py    → health_*.csv / json
    S2  清洗标准化      src/02_cleaning.py             → data/processed/*.parquet
    S3  指标与分组聚合  src/03_metrics_aggregation.py  → agg_*.csv
    S4  时间序列+NumPy  src/04_timeseries_stats.py     → ts_*.csv / thresholds.json
    S5  统计检验        src/05_stat_tests.py           → stat_tests.csv
    S6  可视化          src/06_visualize.py            → outputs/figures/*.png
    S7  质量门禁        src/09_quality_report.py       → quality_*.csv / json
    S8  入库 SQLite     src/07_sqlite_load.py          → outputs/results.db
    S9  SQL 分析查询    src/08_sql_queries.py          → sql_q*.csv / sql_report.md

用法
    python src/run_pipeline.py                # 全量运行（默认）
    python src/run_pipeline.py --fast         # 快速模式：清洗阶段抽样 500 万行
    python src/run_pipeline.py --from S3      # 从指定阶段开始（复用已有产出）
    python src/run_pipeline.py --only S6 S7   # 只跑指定阶段
    python src/run_pipeline.py --list         # 列出阶段

注意
    --fast 会产出抽样数据，仅用于验证流程连通性，不可用于出报告。
    全量运行 S2 阶段处理 1.6 GB CSV（约 37M 行），耗时较长，请耐心等待。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import os 

ENV = os.environ.copy()
ENV["PYTHONIOENCODING"] = "utf-8"
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
LOGDIR = ROOT / "outputs" / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)

PY = sys.executable

# (阶段号, 名称, 脚本, 额外参数, 主要产出)
STAGES = [
    ("S1", "数据体检",         "01_data_health_check.py",  [],                       "outputs/tables/health_report.json"),
    ("S2", "清洗标准化",       "02_cleaning.py",           [],                       "data/processed/action_clean.parquet"),
    ("S3", "指标与分组聚合",   "03_metrics_aggregation.py", [],                      "outputs/tables/agg_overall.csv"),
    ("S4", "时间序列与统计",   "04_timeseries_stats.py",   [],                       "outputs/tables/ts_daily_trend.csv"),
    ("S5", "统计检验",         "05_stat_tests.py",         [],                       "outputs/tables/stat_tests.csv"),
    ("S6", "可视化",           "06_visualize.py",          [],                       "outputs/figures/fig01_funnel.png"),
    ("S7", "质量门禁",         "09_quality_report.py",     [],                       "outputs/tables/quality_summary.json"),
    ("S8", "入库 SQLite",      "07_sqlite_load.py",        [],                       "outputs/results.db"),
    ("S9", "SQL 分析查询",     "08_sql_queries.py",        [],                       "outputs/sql_report.md"),
]


def hr(c: str = "=") -> None:
    print(c * 66, flush=True)


def run_stage(sid: str, name: str, script: str, extra: list[str]) -> dict:
    hr()
    print(f"[{sid}] {name}  ({script})", flush=True)
    hr("-")
    path = SRC / script
    if not path.exists():
        print(f"  [跳过] 脚本不存在：{path}", flush=True)
        return {"stage": sid, "name": name, "status": "missing", "seconds": 0, "returncode": None}

    t0 = time.time()
    logf = LOGDIR / f"{sid}_{script.replace('.py', '')}.log"
    try:
        with open(logf, "w", encoding="utf-8") as f:
            p = subprocess.run(
                [PY, str(path), *extra],
                cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",env=ENV
            )
        rc = p.returncode
    except Exception as e:
        print(f"  [异常] {type(e).__name__}: {e}", flush=True)
        rc = -1

    dt = round(time.time() - t0, 1)
    status = "ok" if rc == 0 else "fail"

    # 回显日志尾部，便于观察进度
    try:
        lines = logf.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        tail = lines[-8:] if len(lines) > 8 else lines
        for l in tail:
            print(f"    | {l}", flush=True)
    except Exception:
        pass

    icon = "✅" if rc == 0 else "❌"
    print(f"  {icon} [{sid}] {name} 完成 rc={rc}  耗时 {dt}s  日志：{logf.name}", flush=True)
    return {"stage": sid, "name": name, "status": status,
            "seconds": dt, "returncode": rc, "log": logf.name}


def verify_outputs() -> list[dict]:
    """校验关键产出是否存在。"""
    checks = [
        ("清洗数据", "data/processed/action_clean.parquet"),
        ("聚合结果", "outputs/tables/agg_overall.csv"),
        ("漏斗结果", "outputs/tables/agg_funnel_overall.csv"),
        ("趋势结果", "outputs/tables/ts_daily_trend.csv"),
        ("异常样本", "outputs/tables/anomaly_samples.csv"),
        ("统计检验", "outputs/tables/stat_tests.csv"),
        ("质量规则", "outputs/tables/quality_rules.csv"),
        ("SQLite",   "outputs/results.db"),
        ("SQL 报告", "outputs/sql_report.md"),
        ("图表目录", "outputs/figures"),
    ]
    out = []
    for name, rel in checks:
        p = ROOT / rel
        ok = p.exists()
        size = ""
        if ok and p.is_file():
            size = f"{p.stat().st_size/1024/1024:.2f} MB" if p.stat().st_size > 1024*100 else f"{p.stat().st_size/1024:.1f} KB"
        elif ok:
            size = f"{len(list(p.glob('*.png')))} 张图"
        out.append({"检查项": name, "路径": rel, "存在": ok, "大小": size if ok else "—"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="京东数据分析一键流水线")
    ap.add_argument("--fast", action="store_true", help="清洗阶段抽样 500 万行（仅验证流程）")
    ap.add_argument("--from", dest="start", metavar="S3", help="从指定阶段开始")
    ap.add_argument("--only", nargs="+", metavar="S", help="只运行指定阶段")
    ap.add_argument("--list", action="store_true", help="列出阶段")
    args = ap.parse_args()

    if args.list:
        print("流水线阶段：")
        for sid, name, script, _, prod in STAGES:
            print(f"  {sid}  {name:14s} {script:26s} → {prod}")
        return 0

    plan = STAGES
    if args.only:
        want = {s.upper() for s in args.only}
        plan = [s for s in STAGES if s[0] in want]
    elif args.start:
        ids = [s[0] for s in STAGES]
        if args.start.upper() not in ids:
            print(f"[错误] 未知阶段 {args.start}，可选：{ids}")
            return 2
        plan = STAGES[ids.index(args.start.upper()):]

    hr()
    print(f"京东电商用户消费数据分析 · 一键流水线")
    print(f"  开始时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  运行阶段：{', '.join(s[0] for s in plan)}")
    print(f"  模式：{'FAST（抽样，仅供验证）' if args.fast else 'FULL（全量）'}")
    print(f"  Python：{PY}")
    hr()

    t_all = time.time()
    results: list[dict] = []
    for sid, name, script, extra, _ in plan:
        extra2 = list(extra)
        if args.fast and script == "02_cleaning.py":
            extra2.append("--sample")
        r = run_stage(sid, name, script, extra2)
        results.append(r)
        if r["status"] == "fail":
            hr()
            print(f"❌ 流水线中断于 [{sid}] {name}（rc={r['returncode']}）")
            print(f"   日志：{(LOGDIR / str(r.get('log','')))}")
            print(f"   建议：修复后执行  python scripts/run_pipeline.py --from {sid}")
            _write_summary(results, t_all, aborted=sid)
            return 1
        if r["status"] == "missing":
            print(f"   (该阶段脚本缺失，继续后续阶段)")

    hr()
    print("产出校验")
    checks = verify_outputs()
    okc = sum(1 for c in checks if c["存在"])
    for c in checks:
        print(f"  {'✅' if c['存在'] else '❌'} {c['检查项']:10s} {c['路径']:46s} {c['大小']}")

    total = round(time.time() - t_all, 1)
    hr()
    print(f"🎉 流水线完成　阶段 {len(results)} 个　总耗时 {total}s（{total/60:.1f} 分钟）")
    print(f"   产出校验 {okc}/{len(checks)} 通过")
    hr()
    print("下一步：")
    print("  启动看板：  streamlit run app/dashboard.py")
    print("  查看报告：  outputs/report_evaluation.md")
    print("  执行 SQL：  python src/08_sql_queries.py")
    _write_summary(results, t_all)
    return 0


def _write_summary(results: list[dict], t_all: float, aborted: str | None = None) -> None:
    s = {
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_seconds": round(time.time() - t_all, 1),
        "aborted_at": aborted,
        "stages": results,
        "outputs_check": verify_outputs(),
    }
    (LOGDIR / "pipeline_summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n  流水线摘要：outputs/logs/pipeline_summary.json")


if __name__ == "__main__":
    sys.exit(main())
