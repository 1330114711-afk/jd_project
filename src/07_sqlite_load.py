"""
07_sqlite_load.py — 评估结果入库 SQLite

前置
    outputs/tables/*.csv（聚合 / 趋势 / 检验 / 质量）

输出
    outputs/results.db      SQLite 数据库（单文件，便于分发与 SQL 复现）

设计
    - 每个 CSV 一张表，表名 = 文件名（去 .csv）
    - 列名做 SQL 安全化：中文/特殊字符列名统一转为 ASCII 快照列名，同时保留原名列
    - 写入前 DROP 同名表，保证幂等（可重复运行）
    - 建索引：高频查询列（dt / 指标 / 检验）
    - 记录入库元数据表 _meta（行数、列名映射、入库时间），便于溯源

运行
    python src/07_sqlite_load.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "outputs" / "tables"
DB = ROOT / "outputs" / "results.db"

# 需要入库的表（存在即入）
TABLES = [
    "agg_overall", "agg_funnel_overall", "agg_funnel_by_type", "agg_funnel_by_day",
    "funnel_containment_check",
    "agg_user_funnel_by_level", "agg_user_funnel_by_sex", "agg_user_funnel_by_age",
    "agg_user_funnel_by_city", "agg_user_activity",
    "agg_cate", "agg_brand_top50", "agg_shop_top100",
    "agg_time_daily", "agg_time_hourly", "agg_time_weekday",
    "agg_cate_userlevel", "agg_cate_city",
    "ts_daily_trend", "ts_weekly", "ts_period",
    "stats_summary", "anomaly_by_method", "anomaly_samples",
    "stat_tests", "stat_group_desc",
    "quality_rules", "quality_issues",
]

# 中文列名 -> ASCII 安全名
CN_MAP = {
    "指标": "metric", "指标值": "metric_value", "检验": "test_name", "结论": "conclusion",
    "分组": "grp", "组A": "group_a", "组B": "group_b", "组A_n": "group_a_n", "组B_n": "group_b_n",
    "组A均值": "group_a_mean", "组B均值": "group_b_mean", "差值(A-B)": "diff_a_b",
    "相对变化": "rel_change", "效应量强度": "effect_strength",
    "用户等级": "user_level", "性别": "sex", "年龄段": "age_band", "城市等级": "city_level",
    "星期": "weekday_name", "旬": "period_band",
    "SKU数": "sku_cnt", "行为量": "action_cnt", "下单行为数": "order_cnt",
    "下单用户数": "order_users", "用户数": "user_cnt", "活跃用户数": "active_users",
    "好评率": "good_rate", "差评率": "bad_rate", "行为量份额": "action_share",
    "每SKU行为量": "actions_per_sku", "打卡数": "checkin",
    "浏览_uv": "uv_view", "加购_uv": "uv_cart", "下单_uv": "uv_order",
    "加购率": "cart_rate", "下单率": "order_rate", "加购到下单率": "cart2order_rate",
    "用户份额": "user_share", "行为量占比": "action_share", "行为占比": "action_share",
    "人均行为": "action_per_user", "下单转化率": "order_conv_rate", "活跃用户数_MA7": "active_user_ma7",
    "行为量_MA7": "action_ma7", "下单行为数_MA7": "order_cnt_ma7",
    "日均行为量": "avg_daily_action", "日均活跃用户": "avg_daily_active",
    "日均下单用户": "avg_daily_order_users", "行为量_旬环比": "action_band_mom",
    "行为量_环比": "action_dod", "活跃用户数_环比": "active_dod",
    "行为量_周同比": "action_wow", "行为量_周环比": "action_wow",
    "天数": "n_days", "周起始": "week_start", "周序号": "week_no",
    "是否周末": "is_weekend", "下单用户数合计": "order_users_total",
    "活跃用户数均值": "avg_active",
    "规则": "rule", "级别": "level", "通过": "passed", "问题数": "issue_cnt",
    "占比": "ratio", "说明": "note", "值": "value", "阈值": "threshold",
    "异常数": "anomaly_cnt", "检查项": "check_item",
    "决策": "decision",
    "行为量最小": "action_min", "行为量最大": "action_max", "行为量均值": "action_mean",
    "z_score检出": "z_hits", "IQR检出": "iqr_hits", "MAD检出": "mad_hits",
    "高置信异常(>=2法)": "high_conf_anomalies", "z_warn": "z_warn", "z_crit": "z_crit",
    "方向": "direction", "期望频数<5的格子": "cells_lt5", "反例数": "counterexample_cnt",
    "关系": "relation", "成立": "holds", "样本数": "sample_n",
    "该时段行为占比": "hour_share",
}


def safe_col(c: str) -> str:
    """列名 ASCII 化 + 去特殊字符。"""
    c = str(c).strip()
    if c in CN_MAP:
        return CN_MAP[c]
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", c).strip("_").lower()
    if not s or s[0].isdigit():
        s = "c_" + s
    return s or "col"


def sanitize(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """规范列名，返回 (新表, 原名->新名映射)。"""
    mapping = {}
    cols = []
    for c in df.columns:
        n = safe_col(c)
        while n in cols:                       # 防重名
            n = n + "_2"
        cols.append(n)
        mapping[str(c)] = n
    out = df.copy()
    out.columns = cols
    # 对象列统一为 str，避免 sqlite 报类型错
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].astype(str)
    return out, mapping


def main() -> int:
    print("=" * 60, flush=True)
    print("评估结果入库 SQLite", flush=True)
    print("=" * 60, flush=True)

    if DB.exists():
        print(f"[提示] 已存在 {DB.name}，将覆盖同名表", flush=True)

    conn = sqlite3.connect(DB)
    meta = []

    for name in TABLES:
        p = TAB / f"{name}.csv"
        if not p.exists():
            print(f"  [跳过] {name}.csv 不存在", flush=True)
            continue
        df = pd.read_csv(p, encoding="utf-8-sig")
        if df.empty:
            print(f"  [跳过] {name} 为空表", flush=True)
            continue
        df, mapping = sanitize(df)
        df.to_sql(name, conn, if_exists="replace", index=False)
        meta.append({
            "table": name, "rows": int(len(df)), "cols": int(df.shape[1]),
            "col_map": json.dumps(mapping, ensure_ascii=False),
        })
        print(f"  [入库] {name:26s} {len(df):>7,} 行 × {df.shape[1]} 列", flush=True)

    # 索引
    idx_sql = [
        'CREATE INDEX IF NOT EXISTS idx_ts_daily_dt ON ts_daily_trend(dt)',
        'CREATE INDEX IF NOT EXISTS idx_time_daily_dt ON agg_time_daily(dt)',
        'CREATE INDEX IF NOT EXISTS idx_funnel_day_dt ON agg_funnel_by_day(dt)',
        'CREATE INDEX IF NOT EXISTS idx_anom_metric ON anomaly_samples(metric)',
        'CREATE INDEX IF NOT EXISTS idx_anom_dt ON anomaly_samples(dt)',
        'CREATE INDEX IF NOT EXISTS idx_tests_name ON stat_tests(test_name)',
        'CREATE INDEX IF NOT EXISTS idx_shop_shopid ON agg_shop_top100(shop_id)',
        'CREATE INDEX IF NOT EXISTS idx_cate_code ON agg_cate(cate_code)',
    ]
    for s in idx_sql:
        try:
            conn.execute(s)
        except sqlite3.Error as e:
            print(f"  [warn] 建索引失败：{e}", flush=True)

    # 元数据
    mdf = pd.DataFrame(meta)
    mdf["loaded_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mdf.to_sql("_meta", conn, if_exists="replace", index=False)
    conn.commit()

    # 统计
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"\n===== 入库完成 =====\n  数据库：{DB}\n  表数：{len(tables)}")
    print(f"  表清单：{', '.join(tables)}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
