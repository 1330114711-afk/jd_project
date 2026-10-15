"""
05_stat_tests.py — 统计检验与解释

前置
    data/processed/*.parquet

检验清单
    T1 周末效应检验
        H0：周末与非周末的日行为量分布相同
        方法：Welch t 检验（方差不齐）+ Mann-Whitney U（非参数稳健）+ Levene（方差齐性）
    T2 春节效应检验
        H0：春节假期（2018-02-15~02-21）与常态期日行为量相同
        方法：Welch t 检验 + Cohen's d 效应量 + Mann-Whitney U
    T3 用户等级与下单率关联
        H0：用户等级与「是否下单」独立
        方法：卡方独立性检验 + Cramér's V 效应量
    T4 性别与下单率关联
        方法：卡方独立性检验 + Cramér's V
    T5 城市等级与下单率关联
        方法：卡方独立性检验 + Cramér's V
    T6 漏斗各环节转化率差异
        H0：加购→下单 转化率在不同用户等级间相同
        方法：多组比例卡方（等级 × 是否下单）

输出
    outputs/tables/stat_tests.csv          检验结果总表（含统计量/p值/效应量/结论）
    outputs/tables/stat_tests_effect.csv   效应量与事后说明
    outputs/tables/stat_group_desc.csv     分组描述统计（检验输入的可核对明细）

说明
    显著性水平 α = 0.05；p < 0.05 拒绝 H0。
    大样本下 p 值极易显著，因此同时报告效应量（Cohen's d / Cramér's V）判断实际意义：
      Cohen's d:  0.2 小 / 0.5 中 / 0.8 大
      Cramér's V: 0.1 弱 / 0.3 中 / 0.5 强

运行
    python src/05_stat_tests.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
CSV_KW = dict(index=False, encoding="utf-8-sig")

T_VIEW, T_CART, T_FOCUS, T_ORDER, T_COMMENT = 1, 2, 3, 4, 5
ALPHA = 0.05


def log(m: str) -> None:
    print(m, flush=True)


def save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / f"{name}.csv", **CSV_KW)
    log(f"  [输出] {name}.csv ({len(df):,} 行)")


def verdict(p: float, alpha: float = ALPHA) -> str:
    return "拒绝H0（存在显著差异）" if p < alpha else "不拒绝H0（无显著差异）"


def cohen_d(a: np.ndarray, b: np.ndarray) -> float:
    """合并标准差效应量。"""
    na, nb = len(a), len(b)
    va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
    pooled = np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    return float((np.mean(a) - np.mean(b)) / pooled) if pooled else 0.0


def eff_label_d(d: float) -> str:
    ad = abs(d)
    return "大" if ad >= 0.8 else "中" if ad >= 0.5 else "小" if ad >= 0.2 else "可忽略"


def cramers_v(table: np.ndarray) -> float:
    """Cramér's V 效应量。"""
    chi2 = stats.chi2_contingency(table)[0]
    n = table.sum()
    r, k = table.shape
    denom = n * (min(r, k) - 1)
    return float(np.sqrt(chi2 / denom)) if denom > 0 else 0.0


def eff_label_v(v: float) -> str:
    return "强" if v >= 0.5 else "中" if v >= 0.3 else "弱" if v >= 0.1 else "可忽略"


# ================================================================ T1/T2 均值检验
def test_continuous(name: str, h0: str, group_a: np.ndarray, group_b: np.ndarray,
                    label_a: str, label_b: str, results: list) -> None:
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]

    t_stat, p_t = stats.ttest_ind(a, b, equal_var=False)      # Welch
    u_stat, p_u = stats.mannwhitneyu(a, b, alternative="two-sided")
    lev_stat, p_lev = stats.levene(a, b)
    d = cohen_d(a, b)

    results.append({
        "检验": name, "H0": h0,
        "组A": label_a, "组A_n": len(a), "组A均值": round(float(np.mean(a)), 4),
        "组B": label_b, "组B_n": len(b), "组B均值": round(float(np.mean(b)), 4),
        "差值(A-B)": round(float(np.mean(a) - np.mean(b)), 4),
        "相对变化": round(float(np.mean(a) / np.mean(b) - 1), 6) if np.mean(b) else None,
        "Welch_t": round(float(t_stat), 4), "p_welch": float(f"{p_t:.3e}"),
        "MannWhitney_U": float(u_stat), "p_mannwhitney": float(f"{p_u:.3e}"),
        "Levene_p": float(f"{p_lev:.3e}"),
        "Cohen_d": round(d, 4), "效应量强度": eff_label_d(d),
        "结论": verdict(p_t),
    })


# ================================================================ T3~T5 独立性检验
def test_independence(name: str, h0: str, df: pd.DataFrame, group_col: str,
                      order_col: str, results: list, desc_rows: list,
                      min_cell: int = 5) -> None:
    """group_col: 是否下单(0/1)；order_col: 分组变量"""
    sub = df[[group_col, order_col]].dropna()
    tab = pd.crosstab(sub[order_col], sub[group_col])
    if tab.shape[0] < 2 or tab.shape[1] < 2:
        log(f"  [跳过] {name}：列联表维度不足")
        return

    chi2, p, dof, expected = stats.chi2_contingency(tab)
    v = cramers_v(tab.to_numpy())
    low_cells = int((expected < min_cell).sum())

    results.append({
        "检验": name, "H0": h0,
        "组A": order_col, "组A_n": int(tab.to_numpy().sum()), "组A均值": None,
        "组B": "—", "组B_n": None, "组B均值": None,
        "差值(A-B)": None, "相对变化": None,
        "chi2": round(float(chi2), 4), "dof": int(dof), "p_chi2": float(f"{p:.3e}"),
        "Cramers_V": round(v, 4), "效应量强度": eff_label_v(v),
        "期望频数<5的格子": low_cells,
        "结论": verdict(p) + ("（注意：存在期望频数<5，卡方近似可能不稳）" if low_cells else ""),
    })

    # 分组描述（行 = 分组取值，列 = 下单数/总数/下单率）
    g = sub.groupby(order_col)[group_col].agg(样本数="size", 下单用户数="sum")
    g["下单率"] = (g["下单用户数"] / g["样本数"]).round(6)
    g = g.reset_index().rename(columns={order_col: "分组"})
    g.insert(0, "检验", name)
    desc_rows.append(g)


# ================================================================ 主流程
def main() -> int:
    log("=" * 60)
    log("统计检验与解释")
    log("=" * 60)

    a = pd.read_parquet(PROCESSED / "action_clean.parquet",
                        columns=["user_id", "type", "dt", "is_weekend"])
    u = pd.read_parquet(PROCESSED / "user_clean.parquet",
                        columns=["user_id", "user_lv_cd", "sex", "city_level", "age"])

    daily = a.groupby("dt").agg(行为量=("user_id", "size"),
                                活跃用户数=("user_id", "nunique")).reset_index()
    daily["is_weekend"] = daily["dt"].dt.weekday >= 5
    log(f"[加载] 日粒度 {len(daily)} 天")

    results: list[dict] = []
    desc_rows: list[pd.DataFrame] = []

    # ---------- T1 周末效应 ----------
    we = daily.loc[daily["is_weekend"], "行为量"].to_numpy()
    wd = daily.loc[~daily["is_weekend"], "行为量"].to_numpy()
    test_continuous(
        "T1 周末效应（日行为量）",
        "H0: 周末与非周末日行为量均值相同",
        we, wd, "周末", "工作日", results,
    )
    # 活跃用户同理
    we_u = daily.loc[daily["is_weekend"], "活跃用户数"].to_numpy()
    wd_u = daily.loc[~daily["is_weekend"], "活跃用户数"].to_numpy()
    test_continuous(
        "T1b 周末效应（日活跃用户）",
        "H0: 周末与非周末日活跃用户均值相同",
        we_u, wd_u, "周末", "工作日", results,
    )

    # ---------- T2 春节效应 ----------
    cny_lo, cny_hi = pd.Timestamp("2018-02-15"), pd.Timestamp("2018-02-21")
    cny = daily.loc[daily["dt"].between(cny_lo, cny_hi), "行为量"].to_numpy()
    normal = daily.loc[~daily["dt"].between(cny_lo, cny_hi), "行为量"].to_numpy()
    test_continuous(
        "T2 春节假期效应（日行为量）",
        "H0: 春节假期与常态期日行为量均值相同",
        cny, normal, "春节假期(2/15-2/21)", "常态期", results,
    )

    # ---------- 构建用户级下单标记 ----------
    log("[构建] 用户级下单标记")
    order_users = set(a.loc[a["type"] == T_ORDER, "user_id"].unique())
    view_users = set(a.loc[a["type"] == T_VIEW, "user_id"].unique())
    u = u[u["user_id"].isin(view_users)].copy()          # 以浏览用户为分母
    u["是否下单"] = u["user_id"].isin(order_users).astype(int)
    u = u.drop(columns=["user_id"])
    log(f"  浏览用户 {len(u):,}，其中下单 {int(u['是否下单'].sum()):,}"
        f"（下单率 {u['是否下单'].mean():.4f}）")

    # ---------- T3~T5 独立性 ----------
    test_independence("T3 用户等级 × 是否下单", "H0: 用户等级与是否下单独立",
                      u, "是否下单", "user_lv_cd", results, desc_rows)
    test_independence("T4 性别 × 是否下单", "H0: 性别与是否下单独立",
                      u, "是否下单", "sex", results, desc_rows)
    test_independence("T5 城市等级 × 是否下单", "H0: 城市等级与是否下单独立",
                      u, "是否下单", "city_level", results, desc_rows)
    test_independence("T6 年龄段 × 是否下单", "H0: 年龄段与是否下单独立",
                      u, "是否下单", "age", results, desc_rows)

    # ---------- 输出 ----------
    res = pd.DataFrame(results)
    save(res, "stat_tests")
    if desc_rows:
        save(pd.concat(desc_rows, ignore_index=True), "stat_group_desc")

    # 显著性汇总
    sig = res[res["p_welch"].notna()] if "p_welch" in res.columns else res.iloc[0:0]
    n_sig = int((res["结论"].astype(str).str.startswith("拒绝")).sum())
    with open(OUT / "stat_tests_summary.json", "w", encoding="utf-8") as f:
        json.dump({
            "alpha": ALPHA,
            "n_tests": len(res),
            "n_reject_h0": n_sig,
            "note": "大样本下 p 值易显著，须结合效应量判断实际意义",
        }, f, ensure_ascii=False, indent=2)

    log("\n===== 检验完成 =====")
    for _, r in res.iterrows():
        extra = r.get("Cohen_d") if pd.notna(r.get("Cohen_d")) else r.get("Cramers_V")
        log(f"  {r['检验']}: {r['结论']}  效应量={extra} ({r['效应量强度']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
