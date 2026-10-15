"""
09_quality_report.py — 数据质量与异常报告

前置
    data/processed/*.parquet

定位
    与 01_data_health_check.py 区分：
      01 是「体检」——描述数据长什么样（结构/缺失/取值域）；
      09 是「质量门禁」——用可判定的规则给数据打分，输出通过/不通过，
         并把越界明细落盘，供报告与看板引用。

规则清单（每条含 级别 / 判定逻辑 / 通过条件）
    R01 主键唯一            error  各表主键重复数 == 0
    R02 关键字段非空        error  user_id / sku_id / action_time / type 空值 == 0
    R03 行为类型域合法      error  type ∈ {1,2,3,4,5}
    R04 时间域合法          error  action_dt 落在 [2018-02-01, 2018-04-15]
    R05 时间解析无失败      error  action_dt 非空比例 == 100%
    R06 评论勾稽            error  good + bad <= comments 恒成立
    R07 店铺评分域          warn   shop_score ∈ [0,10] 或 空（占位值已清）
    R08 粉丝/会员非负       warn   fans_num / vip_num >= 0
    R09 漏斗包含关系        warn   浏览 ⊆ 加购（业务链路自洽）
    R10 用户画像覆盖率      warn   行为表可关联 user 的比例 >= 90%
    R11 商品关联覆盖率      warn   行为表可关联 product 的比例 >= 95%
    R12 年龄取值域          warn   age ∈ {1..6}（编码域）

输出
    outputs/tables/quality_rules.csv     规则清单与通过情况
    outputs/tables/quality_issues.csv    未通过项明细（含样例）
    outputs/tables/quality_summary.json  总体质量分

运行
    python src/09_quality_report.py
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

T_VIEW, T_CART, T_FOCUS, T_ORDER, T_COMMENT = 1, 2, 3, 4, 5
# 时间域须按「日期」比较：DATE_MAX 当天的时间戳（如 23:59:59）也应合法
DATE_MIN = pd.Timestamp("2018-02-01")
DATE_MAX_EXCL = pd.Timestamp("2018-04-16")   # 上界取开区间，覆盖 04-15 全天

_rules: list[dict] = []
_issues: list[dict] = []


def log(m: str) -> None:
    print(m, flush=True)


def add_rule(rid, name, level, target, passed, detail, bad_cnt=0):
    _rules.append({
        "规则": rid, "检查项": name, "级别": level, "对象": target,
        "通过": bool(passed), "问题数": int(bad_cnt), "说明": detail,
    })
    if not passed:
        _issues.append({
            "规则": rid, "检查项": name, "级别": level,
            "对象": target, "问题数": int(bad_cnt), "说明": detail,
        })
    flag = "PASS" if passed else "FAIL"
    log(f"  [{flag}] {rid} {name}  {detail}")


# ================================================================ 主流程
def main() -> int:
    log("=" * 60)
    log("数据质量与异常报告")
    log("=" * 60)

    a = pd.read_parquet(PROCESSED / "action_clean.parquet")
    u = pd.read_parquet(PROCESSED / "user_clean.parquet")
    p = pd.read_parquet(PROCESSED / "product_clean.parquet")
    s = pd.read_parquet(PROCESSED / "shop_clean.parquet")
    c = pd.read_parquet(PROCESSED / "comment_clean.parquet")
    log(f"[加载] action {len(a):,} / user {len(u):,} / product {len(p):,} "
        f"/ shop {len(s):,} / comment {len(c):,}")

    # ---- R01 主键唯一 ----
    dups = {
        "user": int(len(u) - u["user_id"].nunique()),
        "product": int(len(p) - p["sku_id"].nunique()),
        "shop": int(len(s) - s["shop_id"].nunique()),
    }
    ckey = c["date_str"].astype(str) + "|" + c["sku_id"].astype(str)
    dups["comment"] = int(len(c) - ckey.nunique())
    total_dup = sum(dups.values())
    add_rule("R01", "主键唯一", "error", "user/product/shop/comment", total_dup == 0,
             f"重复行合计 {total_dup}（{dups}）", total_dup)

    # ---- R02 关键字段非空 ----
    key_null = int(a[["user_id", "sku_id", "action_time", "type"]].isna().any(axis=1).sum())
    add_rule("R02", "关键字段非空", "error", "action", key_null == 0,
             f"空值行 {key_null}", key_null)

    # ---- R03 行为类型域 ----
    valid_t = {T_VIEW, T_CART, T_FOCUS, T_ORDER, T_COMMENT}
    bad_t = int((~a["type"].isin(valid_t)).sum())
    add_rule("R03", "行为类型域合法", "error", "action.type", bad_t == 0,
             f"越界 {bad_t}（合法域 {sorted(valid_t)}）", bad_t)

    # ---- R04 时间域 ----
    # 用半开区间 [DATE_MIN, DATE_MAX_EXCL)，避免把末日当天的时间戳误判为越界
    td = a["action_dt"]
    bad_time = int((~((td >= DATE_MIN) & (td < DATE_MAX_EXCL))).sum())
    add_rule("R04", "时间域合法", "error", "action.action_dt", bad_time == 0,
             f"越界 {bad_time}（域 {DATE_MIN.date()}~2018-04-15 全天）", bad_time)

    # ---- R05 时间解析无失败 ----
    null_time = int(a["action_dt"].isna().sum())
    add_rule("R05", "时间解析无失败", "error", "action.action_dt",
             null_time == 0, f"解析失败 {null_time}", null_time)

    # ---- R06 评论勾稽 ----
    viol = int((c["good_comments"] + c["bad_comments"] > c["comments"]).sum())
    add_rule("R06", "评论勾稽 good+bad<=comments", "error", "comment", viol == 0,
             f"违规 {viol}", viol)

    # ---- R07 店铺评分域 ----
    sc = s["shop_score"].dropna()
    bad_sc = int(((sc < 0) | (sc > 10)).sum())
    add_rule("R07", "店铺评分域 [0,10]", "warn", "shop.shop_score", bad_sc == 0,
             f"越界 {bad_sc}，无效占位已转空 {int(s['shop_score'].isna().sum())} 条", bad_sc)

    # ---- R08 粉丝/会员非负 ----
    bad_f = int((s["fans_num"] < 0).sum() + (s["vip_num"] < 0).sum())
    add_rule("R08", "粉丝/会员非负", "warn", "shop.fans_num/vip_num", bad_f == 0,
             f"负值 {bad_f}", bad_f)

    # ---- R09 漏斗包含关系 ----
    sv = set(a.loc[a["type"] == T_VIEW, "user_id"])
    sc_ = set(a.loc[a["type"] == T_CART, "user_id"])
    not_contained = len(sv - sc_)
    add_rule("R09", "漏斗包含 浏览 ⊆ 加购", "warn", "action", not_contained == 0,
             f"不成立（浏览中 {not_contained:,} 人无加购记录）"
             f"→ 评估需用严格嵌套口径", not_contained)

    # ---- R10 画像覆盖率 ----
    cov_u = float(a["user_has_profile"].mean())
    add_rule("R10", "用户画像覆盖率>=90%", "warn", "action.user_id", cov_u >= 0.90,
             f"实际 {cov_u:.2%}（{1-cov_u:.2%} 行为无法关联画像）", int((~a["user_has_profile"]).sum()))

    # ---- R11 商品关联覆盖率 ----
    cov_p = float(a["sku_has_product"].mean())
    add_rule("R11", "商品关联覆盖率>=95%", "warn", "action.sku_id", cov_p >= 0.95,
             f"实际 {cov_p:.2%}", int((~a["sku_has_product"]).sum()))

    # ---- R12 年龄域 ----
    age = u["age"].dropna()
    bad_age = int((~age.isin([1, 2, 3, 4, 5, 6])).sum())
    add_rule("R12", "年龄取值域 {1..6}", "warn", "user.age", bad_age == 0,
             f"越界 {bad_age}（age 为年龄段编码，非实际年龄）", bad_age)

    # ---- 落盘 ----
    rd = pd.DataFrame(_rules)
    rd.to_csv(OUT / "quality_rules.csv", index=False, encoding="utf-8-sig")
    idf = pd.DataFrame(_issues) if _issues else pd.DataFrame(
        columns=["规则", "检查项", "级别", "对象", "问题数", "说明"])
    idf.to_csv(OUT / "quality_issues.csv", index=False, encoding="utf-8-sig")

    n_err = int(((rd["级别"] == "error") & (~rd["通过"])).sum())
    n_warn = int(((rd["级别"] == "warn") & (~rd["通过"])).sum())
    total = len(rd)
    passed = int(rd["通过"].sum())
    score = round(passed / total * 100, 2) if total else 0

    summary = {
        "n_rules": total,
        "n_passed": passed,
        "n_failed": total - passed,
        "n_error_failed": n_err,
        "n_warn_failed": n_warn,
        "quality_score": score,
        "gate": "BLOCK" if n_err > 0 else ("WARN" if n_warn > 0 else "PASS"),
        "loaded_from": "data/processed/*.parquet",
    }
    with open(OUT / "quality_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log("\n===== 质量评估完成 =====")
    log(f"  规则 {total} 条：通过 {passed}，error 未通过 {n_err}，warn 未通过 {n_warn}")
    log(f"  质量分 {score}/100　门禁：{summary['gate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
