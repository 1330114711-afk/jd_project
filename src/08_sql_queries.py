"""
08_sql_queries.py — SQL 评估分析查询

前置
    outputs/results.db（由 07_sqlite_load.py 产出）

设计
    把评估问题写成可直接执行、可复现的 SQL，覆盖：
      Q1  大盘核心指标一览（严格口径漏斗）
      Q2  日趋势 Top/Bottom 与环比极值
      Q3  异常日明细（高置信异常 + z-score 排序）
      Q4  用户等级画像：规模 / 下单率 排名
      Q5  品类排行与好评率交叉
      Q6  时段节律：小时 × 行为量 热点
      Q7  星期节律与周末效应
      Q8  店铺经营：粉丝/会员/评分 TOP
      Q9  统计检验结论汇总（显著的检验）
      Q10 高低转化用户群对比（分等级下单率极差）

输出
    outputs/tables/sql_q01..q10_*.csv      各查询结果明细
    outputs/sql_report.md                   SQL 查询结果汇总报告（可读）

运行
    python src/08_sql_queries.py
"""

from __future__ import annotations

import sqlite3
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "outputs" / "results.db"
OUT = ROOT / "outputs" / "tables"
OUT.mkdir(parents=True, exist_ok=True)

# (编号, 标题, SQL, 结论解读函数)
QUERIES: list[tuple[str, str, str, str]] = [
    (
        "q01", "大盘核心指标（严格口径漏斗）",
        """
        SELECT
            "index" AS metric,
            c_0     AS value,
            CASE
                WHEN "index" LIKE '%rate%' OR "index" LIKE '%conv%'
                     OR "index" LIKE '%coverage%' THEN '比率'
                ELSE '计数'
            END AS kind
        FROM agg_overall
        WHERE "index" IN (
            'total_action_rows','total_users_active','total_skus','total_shop','total_brands',
            'n_days','funnel_view_strict','funnel_cart_strict','funnel_order_strict',
            'view2cart_rate_strict','cart2order_rate_strict','overall_conv_rate_strict',
            'repurchase_rate','avg_orders_per_user_order','good_rate','bad_rate',
            'user_profile_coverage','sku_product_coverage'
        )
        """,
        "严格口径下，浏览→加购→下单整体转化率即评估基准线；复购率反映用户黏性。",
    ),
    (
        "q02", "日行为量 峰值/谷值 Top5",
        """
        SELECT dt, action_cnt, active_users, order_cnt,
               ROUND(action_dod, 4)  AS dod,
               ROUND(action_wow, 4)  AS wow
        FROM ts_daily_trend
        ORDER BY action_cnt DESC
        LIMIT 5
        """,
        "峰值日通常对应促销脉冲或数据采集高峰，需结合异常检测判定是真实大促还是流量异常。",
    ),
    (
        "q03", "日行为量 谷值 Bottom5",
        """
        SELECT dt, action_cnt, active_users, order_cnt,
               ROUND(action_dod, 4) AS dod
        FROM ts_daily_trend
        ORDER BY action_cnt ASC
        LIMIT 5
        """,
        "谷值多落在春节等假期窗口，说明用户基数受节假日影响显著。",
    ),
    (
        "q04", "高置信异常日明细（≥2 种方法命中）",
        """
        SELECT metric, dt, metric_value,
               ROUND(z_score, 3)      AS z_score,
               ROUND(modified_z, 3)   AS modified_z,
               flag_zscore, flag_iqr, flag_mad,
               anomaly_votes, direction
        FROM anomaly_samples
        ORDER BY metric, dt
        """,
        "多方法一致的异常更可信；偏低型异常集中在特定节假日窗口，偏高型多为采集或大促脉冲。",
    ),
    (
        "q05", "用户等级：规模与下单率",
        """
        SELECT
            user_level,
            uv_view  AS view_users,
            uv_order AS order_users,
            ROUND(order_rate * 100, 2) AS order_rate_pct,
            ROUND(user_share * 100, 2) AS share_pct
        FROM agg_user_funnel_by_level
        ORDER BY view_users DESC
        """,
        "等级越高（数字越大）通常下单率越高；低等级长尾用户规模大但转化弱，是精细化运营重点。",
    ),
    (
        "q06", "品类 TOP10 行为量与口碑",
        """
        SELECT cate_code, sku_cnt, action_cnt, order_users,
               ROUND(action_share * 100, 3) AS action_share_pct,
               ROUND(good_rate * 100, 2)    AS good_rate_pct,
               ROUND(bad_rate * 100, 2)     AS bad_rate_pct
        FROM agg_cate
        ORDER BY action_cnt DESC
        LIMIT 10
        """,
        "头部品类贡献主要流量；需关注是否存在高流量高差评的品类，作为质量改进优先级。",
    ),
    (
        "q07", "时段节律：小时行为量排行",
        """
        SELECT hour, action_cnt, active_users AS uv,
               ROUND(action_share * 100, 3) AS action_share_pct
        FROM agg_time_hourly
        ORDER BY action_cnt DESC
        LIMIT 8
        """,
        "高峰时段是投放与推送的最佳窗口；凌晨低谷适合做系统维护。",
    ),
    (
        "q08", "星期节律与周末效应",
        """
        SELECT weekday, weekday_name, action_cnt, active_users,
               ROUND(action_share * 100, 3) AS action_share_pct
        FROM agg_time_weekday
        ORDER BY weekday
        """,
        "若各星期占比接近，说明不存在显著周末效应，与统计检验结论相互印证。",
    ),
    (
        "q09", "店铺 TOP10（规模与口碑）",
        """
        SELECT shop_id, sku_cnt, action_cnt, order_users,
               fans_num, vip_num,
               ROUND(vip_per_fans * 100, 2) AS vip_conv_pct,
               ROUND(shop_score, 2)         AS shop_score
        FROM agg_shop_top100
        ORDER BY action_cnt DESC
        LIMIT 10
        """,
        "粉丝转会员率高的店铺私域运营更强；评分为空（原值 -1/0）的店铺不参与评分横向比较。",
    ),
    (
        "q10", "统计检验结论汇总",
        """
        SELECT test_name, group_a, group_b, conclusion,
               effect_strength,
               CASE WHEN p_welch  IS NOT NULL THEN ROUND(p_welch, 10) END AS p_welch,
               CASE WHEN p_chi2   IS NOT NULL THEN ROUND(p_chi2, 10)  END AS p_chi2,
               CASE WHEN cohen_d   IS NOT NULL THEN cohen_d END AS cohen_d,
               CASE WHEN cramers_v IS NOT NULL THEN cramers_v END AS cramers_v
        FROM stat_tests
        ORDER BY test_name
        """,
        "显著性只说明差异存在，效应量说明差异是否值得行动；两者需一起读。",
    ),
]


def run() -> int:
    print("=" * 60, flush=True)
    print("SQL 评估分析查询", flush=True)
    print("=" * 60, flush=True)

    if not DB.exists():
        print(f"[错误] 未找到 {DB}，请先运行 src/07_sqlite_load.py", flush=True)
        return 1

    conn = sqlite3.connect(DB)
    results = []
    md_lines = ["# SQL 评估分析查询结果\n",
                f"数据库：`outputs/results.db`　生成脚本：`src/08_sql_queries.py`\n",
                "> 所有结果由 SQL 直接查询数据库产出，可重复执行。\n"]

    for qid, title, sql, note in QUERIES:
        try:
            df = pd.read_sql_query(sql, conn)
        except Exception as e:
            print(f"  [错误] {qid} {title}: {type(e).__name__}: {e}", flush=True)
            continue
        fname = f"sql_{qid}_{_slug(title)}.csv"
        df.to_csv(OUT / fname, index=False, encoding="utf-8-sig")
        results.append((qid, title, df, note))
        print(f"  [查询] {qid} {title} → {len(df)} 行 → {fname}", flush=True)

    conn.close()

    # ---- 生成 SQL 汇总报告 ----
    for qid, title, df, note in results:
        md_lines.append(f"\n## {qid.upper()}　{title}\n")
        md_lines.append(f"```sql\n{_fmt_sql(dict((q[0], q[2]) for q in QUERIES)[qid])}\n```\n")
        md_lines.append(_to_md(df.head(25)))
        if len(df) > 25:
            md_lines.append(f"\n*（共 {len(df)} 行，此处展示前 25 行，完整结果见 csv）*\n")
        md_lines.append(f"\n**解读**：{note}\n")

    (ROOT / "outputs" / "sql_report.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n===== 完成 =====\n  查询 {len(results)} 个\n  报告：outputs/sql_report.md")
    return 0


def _slug(s: str) -> str:
    return (s.replace("（", "_").replace("）", "").replace("：", "_")
             .replace("/", "_").replace(" ", "").replace("，", "_")[:28])


def _fmt_sql(s: str) -> str:
    """去掉查询字符串的公共缩进，输出可读 SQL。"""
    lines = s.strip().splitlines()
    # 计算最小缩进（忽略空行）
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    pad = min(indents) if indents else 0
    return "\n".join(l[pad:].rstrip() if l.strip() else "" for l in lines)


def _fmt_cell(v) -> str:
    """单元格取值 → 字符串；数值抑制科学计数法，千分位分组。

    注意：agg_overall 这类「长表」的 value 列是混合列——
    整数串（37210678）、比率串（0.294725）、日期串（2018-02-01）混在一起。
    因此不能整列 to_numeric（会把日期变 NaN 而放弃转换），
    必须逐格判断：能数值化且不丢精度的按数值格式，否则原样保留。
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v)
    # 纯整数串 → 千分位（不做 float 转换，避免大整数丢精度/科学计数）
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        return f"{int(s):,}"
    # 浮点串 → 去尾零，抑制科学计数法
    try:
        f = float(s)
    except (TypeError, ValueError):
        return s  # 日期等非数值：原样
    # 仅当 "数值串" 与 "原串" 语义一致时才格式化，避免把形如 '1e5' 的串误改
    if f == f and (("e" in s.lower()) or abs(f) < 1e15):
        out = f"{f:,.6f}".rstrip("0").rstrip(".")
        return out if out else "0"
    return s


def _to_md(df: pd.DataFrame) -> str:
    """转 Markdown 表格，并抑制科学计数法，便于阅读。"""
    d = df.apply(lambda col: col.map(_fmt_cell)).astype(str)
    # disable_numparse：阻止 tabulate 把已格式化好的字符串再解析回数字（否则千分位/科学计数会反复横跳）
    return d.to_markdown(index=False, disable_numparse=True)


if __name__ == "__main__":
    sys.exit(run())
