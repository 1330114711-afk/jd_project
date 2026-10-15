"""
04_timeseries_stats.py — 时间序列趋势 + NumPy 统计指标与异常标记

前置
    data/processed/*.parquet（由 02_cleaning.py 产出）

内容
    A. 时间序列与版本趋势
        - 日粒度：活跃用户 / 行为量 / 下单量 / 下单转化率
        - 7 日移动平均、环比（DoD）、周同比（WoW）
        - 周聚合（WOY 周序号）与阶段趋势（按旬分段）
    B. NumPy 统计指标与阈值标记
        - 均值 / 标准差 / 变异系数（手写 NumPy，非 pandas 便捷方法）
        - 分位数 P1 P5 P25 P50 P75 P95 P99 + IQR
        - z-score 异常检测（|z| > 2 / 3 两级）
        - IQR 法（Tukey 1.5 倍）异常检测
        - MAD 稳健 z-score（modified z-score）异常检测
        - 三种方法交叉标记，输出异常样本明细

输出
    outputs/tables/ts_daily_trend.csv        日趋势（含 MA / 环比 / z-score / 标记）
    outputs/tables/ts_weekly.csv             周聚合趋势
    outputs/tables/ts_period.csv             旬分段趋势
    outputs/tables/stats_summary.csv         NumPy 统计指标汇总（各指标的分位/均值/标准差）
    outputs/tables/anomaly_samples.csv       异常样本明细（三法交叉标记）
    outputs/tables/anomaly_by_method.csv     各方法检出数量对比
    outputs/tables/thresholds.json           阈值定义（供下游与看板复用）

运行
    python src/04_timeseries_stats.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
CSV_KW = dict(index=False, encoding="utf-8-sig")

T_VIEW, T_CART, T_FOCUS, T_ORDER, T_COMMENT = 1, 2, 3, 4, 5


def log(m: str) -> None:
    print(m, flush=True)


def save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / f"{name}.csv", **CSV_KW)
    log(f"  [输出] {name}.csv ({len(df):,} 行)")


# ================================================================ A. 时间序列
def build_daily_trend(a: pd.DataFrame) -> pd.DataFrame:
    log("[时间序列] 构建日粒度趋势")
    daily = a.groupby("dt").agg(
        活跃用户数=("user_id", "nunique"),
        行为量=("user_id", "size"),
    )
    ord_ = a[a["type"] == T_ORDER]
    daily["下单行为数"] = ord_.groupby("dt").size()
    daily["下单用户数"] = ord_.groupby("dt")["user_id"].nunique()
    daily = daily.fillna(0).astype({"下单行为数": int, "下单用户数": int})
    daily = daily.sort_index().reset_index()

    # 派生比率
    daily["人均行为"] = daily["行为量"] / daily["活跃用户数"]
    daily["下单转化率"] = daily["下单用户数"] / daily["活跃用户数"]
    daily["周序号"] = daily["dt"].dt.isocalendar().week.astype(int)
    daily["星期"] = daily["dt"].dt.weekday
    daily["是否周末"] = daily["星期"] >= 5

    # ---- 趋势：移动平均 ----
    # 用 NumPy 卷积实现 7 日移动平均（min_periods=1 语义：前 6 天用可得窗口）
    def _ma(x: np.ndarray, w: int) -> np.ndarray:
        """滑动均值，窗口不足时按实际长度平均（对齐 pandas rolling(min_periods=1)）。"""
        out = np.empty_like(x, dtype=float)
        for i, n in enumerate(x):
            lo = max(0, i - w + 1)
            l = min(w, i + 1)
            out[i] = sum(x[lo : i + 1]) / l
        return out

    for col in ["活跃用户数", "行为量", "下单行为数"]:
        daily[f"{col}_MA7"] = np.round(_ma(daily[col].to_numpy(dtype=float), 7), 2)

    # ---- 环比 DoD / 周同比 WoW ----
    daily["行为量_环比"] = daily["行为量"].pct_change().replace([np.inf, -np.inf], np.nan).round(6)
    daily["活跃用户数_环比"] = daily["活跃用户数"].pct_change().replace([np.inf, -np.inf], np.nan).round(6)
    daily["行为量_周同比"] = (
        daily["行为量"] / daily["行为量"].shift(7).replace(0, np.nan) - 1
    ).round(6)
    return daily


def build_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    log("[时间序列] 构建周聚合")
    w = daily.copy()
    w["周起始"] = w["dt"] - pd.to_timedelta(w["星期"], unit="D")
    g = w.groupby(["周序号", "周起始"]).agg(
        天数=("dt", "nunique"),
        行为量=("行为量", "sum"),
        下单行为数=("下单行为数", "sum"),
        活跃用户数均值=("活跃用户数", "mean"),
        下单用户数合计=("下单用户数", "sum"),
    ).reset_index()
    g["日均行为量"] = (g["行为量"] / g["天数"]).round(1)
    g["行为量_周环比"] = g["行为量"].pct_change().replace([np.inf, -np.inf], np.nan).round(6)
    g["活跃用户数均值"] = g["活跃用户数均值"].round(1)
    return g.sort_values("周起始")


def build_period(daily: pd.DataFrame) -> pd.DataFrame:
    log("[时间序列] 构建旬分段趋势")
    d = daily.copy()
    bins = pd.to_datetime(["2018-02-01", "2018-02-11", "2018-02-21",
                           "2018-03-01", "2018-03-11", "2018-03-21",
                           "2018-04-01", "2018-04-16"])
    labels = ["2月上旬", "2月中旬", "2月下旬", "3月上旬", "3月中旬", "3月下旬", "4月上旬"]
    d["旬"] = pd.cut(d["dt"], bins=bins, labels=labels, right=False)
    g = d.groupby("旬", observed=True).agg(
        天数=("dt", "nunique"),
        行为量=("行为量", "sum"),
        下单行为数=("下单行为数", "sum"),
        日均行为量=("行为量", "mean"),
        日均活跃用户=("活跃用户数", "mean"),
        日均下单用户=("下单用户数", "mean"),
    ).reset_index()
    g["日均行为量"] = g["日均行为量"].round(1)
    g["日均活跃用户"] = g["日均活跃用户"].round(1)
    g["日均下单用户"] = g["日均下单用户"].round(1)
    g["行为量_旬环比"] = g["行为量"].pct_change().replace([np.inf, -np.inf], np.nan).round(6)
    return g


# ================================================================ B. NumPy 统计
def np_stats(x: np.ndarray) -> dict:
    """手写 NumPy 统计指标（不使用 pandas 便捷方法）。"""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = x.size
    if n == 0:
        return {}
    mean = np.mean(x)
    std = np.std(x, ddof=0)          # 总体标准差
    std_s = np.std(x, ddof=1) if n > 1 else np.nan  # 样本标准差
    q = np.percentile(x, [1, 5, 25, 50, 75, 95, 99])
    q1, q3 = q[2], q[4]
    iqr = q3 - q1
    mad = np.median(np.abs(x - np.median(x)))
    return {
        "n": int(n),
        "mean": round(mean, 4),
        "std_pop": round(std, 4),
        "std_sample": round(float(std_s), 4) if not np.isnan(std_s) else None,
        "cv": round(float(std / mean), 6) if mean else None,
        "min": round(float(np.min(x)), 4),
        "max": round(float(np.max(x)), 4),
        "range": round(float(np.max(x) - np.min(x)), 4),
        "p01": round(float(q[0]), 4),
        "p05": round(float(q[1]), 4),
        "p25": round(float(q[2]), 4),
        "p50": round(float(q[3]), 4),
        "p75": round(float(q[4]), 4),
        "p95": round(float(q[5]), 4),
        "p99": round(float(q[6]), 4),
        "iqr": round(float(iqr), 4),
        "mad": round(float(mad), 4),
        # Tukey 围栏
        "lower_fence": round(float(q1 - 1.5 * iqr), 4),
        "upper_fence": round(float(q3 + 1.5 * iqr), 4),
        "skew": round(float(np.mean(((x - mean) / std) ** 3)), 4) if std else None,
        "kurtosis": round(float(np.mean(((x - mean) / std) ** 4) - 3), 4) if std else None,
    }


def flag_anomalies(daily: pd.DataFrame, col: str) -> pd.DataFrame:
    """
    三种独立方法做异常标记，交叉比对：
      1. z-score      |z| > 2 (warn) / > 3 (crit)
      2. IQR (Tukey)  超出 [Q1-1.5IQR, Q3+1.5IQR]
      3. MAD 稳健     modified z = 0.6745*(x-median)/MAD，|mz| > 3.5
    """
    x = daily[col].to_numpy(dtype=float)
    mean, std = np.mean(x), np.std(x)
    med = np.median(x)
    q1, q3 = np.percentile(x, [25, 75])
    iqr = q3 - q1
    mad = np.median(np.abs(x - med))

    z = (x - mean) / std if std else np.zeros_like(x)
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    mz = 0.6745 * (x - med) / mad if mad else np.zeros_like(x)

    out = daily[["dt", col]].copy()
    out["z_score"] = np.round(z, 4)
    out["modified_z"] = np.round(mz, 4)
    out["iqr_lower"] = round(float(lo), 2)
    out["iqr_upper"] = round(float(hi), 2)

    out["flag_zscore"] = np.where(np.abs(z) > 3, "crit", np.where(np.abs(z) > 2, "warn", "ok"))
    out["flag_iqr"] = np.where((x < lo) | (x > hi), "outlier", "ok")
    out["flag_mad"] = np.where(np.abs(mz) > 3.5, "outlier", "ok")

    # 投票：至少 2 种方法判为异常才算高置信异常
    votes = (
        (out["flag_zscore"] != "ok").astype(int)
        + (out["flag_iqr"] != "ok").astype(int)
        + (out["flag_mad"] != "ok").astype(int)
    )
    out["anomaly_votes"] = votes
    out["is_anomaly"] = votes >= 2
    out["direction"] = np.where(x > med, "偏高", "偏低")
    return out


# ================================================================ 主流程
def main() -> int:
    log("=" * 60)
    log("时间序列趋势 + NumPy 统计指标与异常标记")
    log("=" * 60)

    a = pd.read_parquet(PROCESSED / "action_clean.parquet",
                        columns=["user_id", "type", "dt", "hour", "weekday", "is_weekend"])
    log(f"[加载] action {len(a):,} 行")

    # ---- A. 时间序列 ----
    daily = build_daily_trend(a)
    save(daily, "ts_daily_trend")

    weekly = build_weekly(daily)
    save(weekly, "ts_weekly")

    period = build_period(daily)
    save(period, "ts_period")

    # ---- B. NumPy 统计指标 ----
    log("[统计] NumPy 指标汇总")
    targets = {
        "日行为量": daily["行为量"].to_numpy(),
        "日活跃用户数": daily["活跃用户数"].to_numpy(),
        "日下单行为数": daily["下单行为数"].to_numpy(),
        "日下单用户数": daily["下单用户数"].to_numpy(),
        "日下单转化率": daily["下单转化率"].to_numpy(),
        "人均行为": daily["人均行为"].to_numpy(),
    }
    rows = []
    for name, arr in targets.items():
        st = np_stats(arr)
        st = {"指标": name, **st}
        rows.append(st)
    summary = pd.DataFrame(rows)
    save(summary, "stats_summary")

    # ---- 异常标记 ----
    log("[统计] 三法异常检测")
    anom_frames = []
    for col in ["行为量", "活跃用户数", "下单行为数"]:
        f = flag_anomalies(daily, col)
        f = f.rename(columns={col: "指标值"})
        f["指标"] = col
        anom_frames.append(f)
    all_anom = pd.concat(anom_frames, ignore_index=True)

    # 各方法检出对比
    cmp_rows = []
    for col, f in zip(["行为量", "活跃用户数", "下单行为数"], anom_frames):
        cmp_rows.append({
            "指标": col,
            "z_score检出": int((f["flag_zscore"] != "ok").sum()),
            "z_warn": int((f["flag_zscore"] == "warn").sum()),
            "z_crit": int((f["flag_zscore"] == "crit").sum()),
            "IQR检出": int((f["flag_iqr"] != "ok").sum()),
            "MAD检出": int((f["flag_mad"] != "ok").sum()),
            "高置信异常(>=2法)": int(f["is_anomaly"].sum()),
        })
    save(pd.DataFrame(cmp_rows), "anomaly_by_method")

    # 异常样本明细（仅高置信）
    samples = all_anom[all_anom["is_anomaly"]].copy()
    samples["dt"] = samples["dt"].dt.strftime("%Y-%m-%d")
    save(samples.sort_values(["指标", "dt"]), "anomaly_samples")

    # 阈值落盘
    thr = {
        "method": "z-score(|z|>2 warn, >3 crit) + IQR(Tukey 1.5) + MAD(modified z, |mz|>3.5)",
        "decision_rule": ">=2 种方法判为异常 => 高置信异常",
        "per_metric": {},
    }
    for name, arr in targets.items():
        st = np_stats(arr)
        thr["per_metric"][name] = {
            "mean": st["mean"], "std": st["std_pop"],
            "p05": st["p05"], "p95": st["p95"],
            "lower_fence": st["lower_fence"], "upper_fence": st["upper_fence"],
            "z2_low": round(st["mean"] - 2 * st["std_pop"], 2),
            "z2_high": round(st["mean"] + 2 * st["std_pop"], 2),
            "z3_low": round(st["mean"] - 3 * st["std_pop"], 2),
            "z3_high": round(st["mean"] + 3 * st["std_pop"], 2),
        }
    with open(OUT / "thresholds.json", "w", encoding="utf-8") as f:
        json.dump(thr, f, ensure_ascii=False, indent=2)
    log("  [输出] thresholds.json")

    log("\n===== 完成 =====")
    log(f"  日趋势 {len(daily)} 天，高置信异常 {int(all_anom['is_anomaly'].sum())} 条")
    log(f"  峰值日 {daily.loc[daily['行为量'].idxmax(),'dt'].date()} "
        f"({int(daily['行为量'].max()):,})")
    log(f"  谷值日 {daily.loc[daily['行为量'].idxmin(),'dt'].date()} "
        f"({int(daily['行为量'].min()):,})")


if __name__ == "__main__":
    main()
