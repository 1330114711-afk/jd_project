"""
06_visualize.py — Matplotlib 评估可视化

前置
    outputs/tables/*.csv（由 03/04/05 脚本产出）

输出（outputs/figures/*.png，150 dpi）
    fig01_funnel.png            漏斗图（含转化率与流失率标注）
    fig02_daily_trend.png       日趋势：行为量 + MA7 + 异常点标记
    fig03_anomaly_zscore.png    z-score 控制图（±2σ/±3σ 阈值带）
    fig04_hourly_heatmap.png    星期 × 小时 行为热力图
    fig05_user_level.png        用户等级漏斗与下单率
    fig06_cate_top.png          品类 TOP15 行为量
    fig07_stats_box.png         各指标箱线图（含 IQR 围栏）
    fig08_period_trend.png      旬分段趋势（柱 + 折线双轴）

字体
    Windows 下自动探测中文字体（微软雅黑/黑体/宋体），避免方块乱码。

运行
    python src/06_visualize.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "outputs" / "tables"
FIG = ROOT / "outputs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 中文字体
def setup_cjk_font() -> str:
    candidates = ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC",
                  "Source Han Sans SC", "WenQuanYi Micro Hei"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for c in candidates:
        if c in available:
            plt.rcParams["font.sans-serif"] = [c]
            plt.rcParams["axes.unicode_minus"] = False
            return c
    plt.rcParams["axes.unicode_minus"] = False
    return "(未找到中文字体，可能显示方块)"


FONT = setup_cjk_font()

# ---------------------------------------------------------------- 主题
BG = "#ffffff"
FG = "#1f2937"
GRID = "#e5e7eb"
C_BLUE, C_RED, C_GREEN, C_ORANGE, C_PURPLE = "#2563eb", "#dc2626", "#16a34a", "#ea580c", "#7c3aed"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG,
    "axes.edgecolor": GRID, "axes.labelcolor": FG,
    "xtick.color": FG, "ytick.color": FG, "text.color": FG,
    "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "figure.dpi": 150, "savefig.bbox": "tight", "savefig.facecolor": BG,
})


def log(m: str) -> None:
    print(m, flush=True)


def finish(fig, name: str) -> None:
    p = FIG / name
    fig.savefig(p)
    plt.close(fig)
    log(f"  [图] {name}")


def load(n: str) -> pd.DataFrame:
    return pd.read_csv(TAB / f"{n}.csv", encoding="utf-8-sig")


# ================================================================ 图 01 漏斗
def fig_funnel() -> None:
    d = load("agg_funnel_overall")
    stages = d["stage"].tolist()
    uv = d["uv_loose"].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    colors = [C_BLUE, C_ORANGE, C_GREEN]
    y = np.arange(len(stages))[::-1]
    bars = ax.barh(y, uv, color=colors[:len(stages)], height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(stages, fontsize=12)
    ax.set_xlabel("用户数")

    mx = uv.max()
    for i, (b, v) in enumerate(zip(bars, uv)):
        ax.text(v + mx * 0.01, b.get_y() + b.get_height() / 2,
                f"{int(v):,}", va="center", fontsize=11, fontweight="bold")
        if i > 0:
            conv = uv[i] / uv[i - 1]
            ax.text(mx * 0.6, b.get_y() + b.get_height() / 2,
                    f"转化 {conv:.1%}｜流失 {1-conv:.1%}", va="center",
                    fontsize=10, color="#374151",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#f3f4f6", ec=GRID))

    ax.set_xlim(0, mx * 1.18)
    ax.set_title("用户行为漏斗（浏览 → 加购 → 下单）")
    finish(fig, "fig01_funnel.png")


# ================================================================ 图 02 日趋势
def fig_daily_trend() -> None:
    d = load("ts_daily_trend")
    d["dt"] = pd.to_datetime(d["dt"])
    an = load("anomaly_samples")
    an["dt"] = pd.to_datetime(an["dt"])
    an = an[an["指标"] == "行为量"]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(d["dt"], d["行为量"], color=C_BLUE, lw=1.4, alpha=0.55, label="日行为量")
    ax.plot(d["dt"], d["行为量_MA7"], color=C_RED, lw=2.2, label="7日移动平均")

    if len(an):
        m = d.merge(an[["dt"]], on="dt", how="inner")
        ax.scatter(m["dt"], m["行为量"], s=70, color=C_ORANGE, zorder=5,
                   edgecolor="white", lw=1.2, label=f"高置信异常({len(m)}天)")

    # 春节阴影
    ax.axvspan(pd.Timestamp("2018-02-15"), pd.Timestamp("2018-02-21"),
               color="#fde68a", alpha=0.45, label="春节假期")
    ax.axhline(d["行为量"].mean(), color="#9ca3af", ls="--", lw=1, label="均值")

    ax.set_title("日行为量趋势与异常标记")
    ax.set_ylabel("行为量")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.95)
    fig.autofmt_xdate()
    finish(fig, "fig02_daily_trend.png")


# ================================================================ 图 03 z-score 控制图
def fig_anomaly_zscore() -> None:
    d = load("ts_daily_trend")
    d["dt"] = pd.to_datetime(d["dt"])
    x = d["行为量"].to_numpy(dtype=float)
    mean, std = x.mean(), x.std()
    z = (x - mean) / std

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(d["dt"], z, color=C_BLUE, lw=1.5, marker="o", ms=3, label="z-score")
    for lv, c, lb in [(2, C_ORANGE, "±2σ (warn)"), (3, C_RED, "±3σ (crit)")]:
        ax.axhline(lv, color=c, ls="--", lw=1.2, label=lb)
        ax.axhline(-lv, color=c, ls="--", lw=1.2)
    ax.axhline(0, color="#6b7280", lw=1)

    crit = np.abs(z) > 3
    ax.scatter(d["dt"][crit], z[crit], s=80, color=C_RED, zorder=5,
               edgecolor="white", lw=1.2, label=f"|z|>3 ({int(crit.sum())}天)")

    ax.set_title("行为量 z-score 控制图（异常检测）")
    ax.set_ylabel("z-score")
    ax.legend(loc="best", fontsize=9)
    fig.autofmt_xdate()
    finish(fig, "fig03_anomaly_zscore.png")


# ================================================================ 图 04 热力图
def fig_hourly_heatmap() -> None:
    a = pd.read_parquet(ROOT / "data" / "processed" / "action_clean.parquet",
                        columns=["weekday", "hour"])
    piv = a.pivot_table(index="weekday", columns="hour", values="hour",
                        aggfunc="size").fillna(0)
    piv = piv.reindex(index=range(7), columns=range(24), fill_value=0)
    # 每行归一化为该小时的占比（消除星期基数差异）
    norm = piv.to_numpy(dtype=float)
    norm = norm / norm.sum(axis=1, keepdims=True)

    fig, ax = plt.subplots(figsize=(13, 4.2))
    im = ax.imshow(norm, aspect="auto", cmap="YlGnBu")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h}" for h in range(24)], fontsize=8)
    ax.set_yticks(range(7))
    ax.set_yticklabels(["周一", "周二", "周三", "周四", "周五", "周六", "周日"], fontsize=9)
    ax.set_xlabel("小时")
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, pad=0.015)
    cb.set_label("该时段行为占比", fontsize=9)
    ax.set_title("星期 × 小时 行为分布热力图")
    for i in range(7):
        j = int(np.argmax(norm[i]))
        ax.text(j, i, "▲", ha="center", va="center", color=C_RED, fontsize=10)
    finish(fig, "fig04_hourly_heatmap.png")


# ================================================================ 图 05 用户等级
def fig_user_level() -> None:
    d = load("agg_user_funnel_by_level")
    if "用户等级" not in d.columns:
        log("  [跳过] fig05：缺少 用户等级 列")
        return
    d = d.sort_values("用户等级")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    x = np.arange(len(d))
    axes[0].bar(x - 0.2, d["浏览_uv"], width=0.4, color=C_BLUE, label="浏览用户")
    axes[0].bar(x + 0.2, d["下单_uv"], width=0.4, color=C_GREEN, label="下单用户")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(d["用户等级"], fontsize=9)
    axes[0].set_title("各等级用户规模")
    axes[0].set_ylabel("用户数")
    axes[0].legend(fontsize=9)

    axes[1].bar(x, d["下单率"] * 100, color=C_ORANGE)
    for i, v in enumerate(d["下单率"] * 100):
        axes[1].text(i, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=9)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(d["用户等级"], fontsize=9)
    axes[1].set_title("各等级下单转化率")
    axes[1].set_ylabel("下单率 (%)")
    axes[1].set_ylim(0, (d["下单率"] * 100).max() * 1.25)
    fig.suptitle("用户等级维度评估", fontsize=14, fontweight="bold")
    finish(fig, "fig05_user_level.png")


# ================================================================ 图 06 品类
def fig_cate_top() -> None:
    d = load("agg_cate").nlargest(15, "行为量").sort_values("行为量")
    fig, ax = plt.subplots(figsize=(9, 6))
    bars = ax.barh(d["cate_code"].astype(str), d["行为量"], color=C_PURPLE, height=0.65)
    for b, v in zip(bars, d["行为量"]):
        ax.text(v, b.get_y() + b.get_height() / 2, f" {int(v):,}",
                va="center", fontsize=9)
    ax.set_title("品类 TOP15 行为量（编码未映射，见 data_dictionary）")
    ax.set_xlabel("行为量")
    ax.set_xlim(0, d["行为量"].max() * 1.2)
    finish(fig, "fig06_cate_top.png")


# ================================================================ 图 07 箱线图
def fig_stats_box() -> None:
    d = load("ts_daily_trend")
    cols = ["行为量", "活跃用户数", "下单行为数", "下单用户数"]
    data = [d[c].to_numpy(dtype=float) for c in cols]

    fig, ax = plt.subplots(figsize=(9, 5))
    # matplotlib >= 3.9 用 tick_labels 替代 labels
    try:
        bp = ax.boxplot(data, tick_labels=cols, patch_artist=True, widths=0.6,
                        medianprops=dict(color=C_RED, lw=2))
    except TypeError:
        bp = ax.boxplot(data, labels=cols, patch_artist=True, widths=0.6,
                        medianprops=dict(color=C_RED, lw=2))
    for patch in bp["boxes"]:
        patch.set_facecolor("#dbeafe")
        patch.set_edgecolor(C_BLUE)
    for i, arr in enumerate(data, start=1):
        out = []
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out = arr[(arr < lo) | (arr > hi)]
        if out.size:
            ax.scatter(np.full(out.size, i), out, color=C_ORANGE, s=30, zorder=5)
    ax.set_title("各指标分布箱线图（橙点 = IQR 法离群）")
    ax.set_ylabel("数值")
    ax.tick_params(axis="x", labelsize=9)
    finish(fig, "fig07_stats_box.png")


# ================================================================ 图 08 旬趋势
def fig_period_trend() -> None:
    d = load("ts_period")
    x = np.arange(len(d))
    fig, ax1 = plt.subplots(figsize=(10, 4.8))
    ax1.bar(x, d["行为量"], color="#bfdbfe", label="行为量")
    ax1.set_ylabel("行为量")
    ax1.set_xticks(x)
    ax1.set_xticklabels(d["旬"], fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(x, d["日均下单用户"], color=C_RED, marker="o", lw=2, label="日均下单用户")
    ax2.set_ylabel("日均下单用户", color=C_RED)
    ax2.tick_params(axis="y", colors=C_RED)
    ax2.grid(False)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    ax1.set_title("旬分段趋势：行为量与日均下单用户")
    finish(fig, "fig08_period_trend.png")


# ================================================================ 主流程
def main() -> int:
    log("=" * 60)
    log(f"Matplotlib 可视化  中文字体：{FONT}")
    log("=" * 60)
    for fn in [fig_funnel, fig_daily_trend, fig_anomaly_zscore, fig_hourly_heatmap,
               fig_user_level, fig_cate_top, fig_stats_box, fig_period_trend]:
        try:
            fn()
        except Exception as e:
            log(f"  [错误] {fn.__name__}: {type(e).__name__}: {e}")
    log(f"\n===== 完成 =====\n产出目录：{FIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
