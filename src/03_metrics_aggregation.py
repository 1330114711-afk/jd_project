import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_codes as CFG  # noqa: E402

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------- 行为类型常量
T_VIEW, T_CART, T_FOCUS, T_ORDER, T_COMMENT = 1, 2, 3, 4, 5

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
CSV_KW = dict(index=False, encoding="utf-8")

# ================================================================ 指标字典
METRIC_DICT = [
    # (指标名, 中文名, 口径/公式, 依赖, 粒度)
    ("uv", "活跃用户数", "去重 user_id 计数", "action.user_id", "整体/分组"),
    ("pv", "行为量", "行为记录条数", "action", "整体/分组"),
    ("funnel_uv_{stage}", "漏斗各环节用户数", "该 type 下去重 user_id 数", "action.type", "漏斗"),
    ("conv_rate_{a}_{b}", "环节转化率", "阶段b用户数 / 阶段a用户数", "action.type", "漏斗"),
    ("churn_rate_{a}_{b}", "环节流失率", "1 - 转化率", "action.type", "漏斗"),
    ("overall_conv_rate", "整体转化率", "下单用户数 / 浏览用户数", "action.type", "漏斗"),
    ("order_cnt", "下单行为数", "type=下单 的记录数", "action.type", "整体/分组"),
    ("browse_per_user", "人均浏览", "浏览行为数 / 浏览用户数", "action.type", "分组"),
    ("act_per_user", "人均行为", "行为量 / 活跃用户数", "action", "分组"),
    ("cart_rate", "加购率", "加购用户数 / 浏览用户数", "action.type", "漏斗"),
    ("u2o_conv", "加购到下单转化率", "下单用户数 / 加购用户数", "action.type", "漏斗"),
    ("sku_cnt", "商品数", "去重 sku_id 数", "product", "品类/品牌"),
    ("brand_cnt", "品牌数", "去重 brand 数", "product", "品类"),
    ("shop_cnt", "店铺数", "去重 shop_id 数", "product/shop", "品类"),
    ("fans_num_sum", "粉丝数合计", "fans_num 求和", "shop", "店铺"),
    ("vip_num_sum", "会员数合计", "vip_num 求和", "shop", "店铺"),
    ("vip_conv_rate", "粉丝转会员率", "vip_num / fans_num", "shop", "店铺"),
    ("shop_score_avg", "店铺评分均值", "有效评分(剔除-1,0)均值", "shop.shop_score", "店铺"),
    ("good_rate", "好评率", "good_comments / comments", "comment", "整体/商品"),
    ("bad_rate", "差评率", "bad_comments / comments", "comment", "整体/商品"),
    ("dau", "日活跃用户", "按日去重 user_id 数", "action.dt", "时间"),
    ("order_daily", "日下单量", "按日 type=下单 记录数", "action.dt", "时间"),
    ("hour_share", "时段行为占比", "该小时行为量 / 日行为总量", "action.hour", "时间"),
    ("weekend_ratio", "周末行为占比", "周末行为量 / 总行为量", "action.is_weekend", "时间"),
    ("repurchase_rate", "复购率", "下单行为>1次的用户 / 下单用户数", "action.type", "用户"),
    ("user_act_decile", "用户活跃分位", "按行为次数分 10 档", "action", "用户"),
]


def write_metric_dictionary() -> None:
    df = pd.DataFrame(
        METRIC_DICT, columns=["metric", "name_cn", "formula", "depends_on", "granularity"]
    )
    df["口径置信度"] = np.where(
        df["depends_on"].str.contains("action.type"), "依赖 type 口径", "可用"
    )
    save(df, "metrics_dictionary")

def log(msg):
    print(msg, flush=True)

def save(df, name):
    path = OUT / f"{name}.csv"
    df.to_csv(path, **CSV_KW)
    log(f"  [输出] {name}.csv ({len(df):,} 行)")

# ================================================================ 数据加载
def load():
    log(f"[加载] data/processed/*.parquet")
    d = {}
    for n in ["user","comment","action","shop","product"]:
        p = PROCESSED / f"{n}_clean.parquet"
        d[n] = pd.read_parquet(p)
        log(f"  {n:8s} {len(d[n]):>12,}")
    return d

# ================================================================ 1. 总体指标
def agg_overall(d):
    a = d["action"]
    view_u = a[a["type"] == T_VIEW]["user_id"].nunique()
    cart_u = a[a["type"] == T_CART]["user_id"].nunique()
    order_u = a[a["type"] == T_ORDER]["user_id"].nunique()
    focus_u = a[a["type"] == T_FOCUS]["user_id"].nunique()

    # 严格口径（嵌套交集）：与 agg_funnel_overall 一致
    s_v = set(a.loc[a["type"] == T_VIEW, "user_id"])
    s_c = set(a.loc[a["type"] == T_CART, "user_id"])
    s_o = set(a.loc[a["type"] == T_ORDER, "user_id"])
    strict_cart = len(s_v & s_c)
    strict_order = len(s_v & s_c & s_o)

    total_comments = d['comment']['comments'].sum()
    row = {
        "total_action_rows": len(a),
        "total_users_active": a["user_id"].nunique(),
        "total_skus": d["product"]["sku_id"].nunique(),
        "total_shop": d["shop"]["shop_id"].nunique(),
        "total_brands": d["product"]["brand"].nunique(),
        "date_min": str(a["dt"].min().date()),
        "date_max": str(a["dt"].max().date()),
        "n_days": int(a["dt"].nunique()),
        "view_users": view_u,
        "cart_users": cart_u,
        "order_users": order_u,
        "focus_users": focus_u,
        # ---- 严格口径漏斗（评估采用）----
        "funnel_view_strict": view_u,
        "funnel_cart_strict": strict_cart,
        "funnel_order_strict": strict_order,
        "view2cart_rate_strict": round(strict_cart / view_u, 6) if view_u else None,
        "cart2order_rate_strict": round(strict_order / strict_cart, 6) if strict_cart else None,
        "overall_conv_rate_strict": round(strict_order / view_u, 6) if view_u else None,
        # ---- 宽松口径（仅作对照，勿直接引用）----
        "view2cart_rate_loose": round(cart_u / view_u, 6) if view_u else None,
        "cart2order_rate_loose": round(order_u / cart_u, 6) if cart_u else None,
        "view2order_rate_loose": round(order_u / view_u, 6) if view_u else None,
        "total_comments": int(total_comments),
        "good_rate": round(d['comment']['good_comments'].sum() / total_comments, 6) if total_comments else None,
        "bad_rate": round(d['comment']['bad_comments'].sum() / total_comments, 6) if total_comments else None,
        "user_profile_coverage": round(a["user_has_profile"].mean(), 6),
        "sku_product_coverage": round(a["sku_has_product"].mean(), 6),
    }

    oc = a[a["type"] == T_ORDER].groupby("user_id").size()
    row["repurchase_rate"] = round(int((oc > 1).sum()) / len(oc), 6) if len(oc) else None
    row["avg_orders_per_user_order"] = round(float(oc.mean()), 6) if len(oc) else None
    save(pd.DataFrame([row]).T.reset_index().rename({"index": "metric", 0: "value"}), "agg_overall")
    with open(OUT/"agg_overall.json", "w", encoding='utf-8') as f:
        json.dump(row, f, ensure_ascii=False, indent=2, default=str)

# ================================================================ 2. 漏斗
def agg_funnel_overall(d):
    """
    漏斗两种口径并列输出：
      宽松口径（loose）：各环节独立去重 UV，不要求包含关系 => 可能出现转化率 >100%
      严格口径（strict）：嵌套交集 UV（浏览 → 浏览∩加购 → 浏览∩加购∩下单），转化率必 ≤100%

    本项目数据特点：浏览用户 100% 包含于加购用户（浏览行为可能未被完整记录），
    因此宽松口径会出现"加购 UV > 浏览 UV"、转化率 121% 的反常结果。
    评估报告以【严格口径】为准。
    """
    a = d["action"]
    s_view = set(a.loc[a["type"] == T_VIEW, "user_id"].unique())
    s_cart = set(a.loc[a["type"] == T_CART, "user_id"].unique())
    s_order = set(a.loc[a["type"] == T_ORDER, "user_id"].unique())

    # 严格嵌套口径
    strict = {
        "浏览": len(s_view),
        "加购": len(s_view & s_cart),
        "下单": len(s_view & s_cart & s_order),
    }
    # 宽松独立口径
    loose = {"浏览": len(s_view), "加购": len(s_cart), "下单": len(s_order)}
    pv_map = {t: int((a["type"] == t).sum()) for t in (T_VIEW, T_CART, T_ORDER)}
    names = [(T_VIEW, "浏览"), (T_CART, "加购"), (T_ORDER, "下单")]

    rows = []
    prev_s = prev_l = None
    base = strict["浏览"]
    for i, (t, name) in enumerate(names):
        r = {
            "stage": name, "type": t, "stage_order": i + 1,
            "pv": pv_map[t],
            "uv_strict": strict[name], "uv_loose": loose[name],
        }
        if prev_s is not None:
            r["conv_strict"] = round(strict[name] / prev_s, 6) if prev_s else None
            r["churn_strict"] = round(1 - strict[name] / prev_s, 6) if prev_s else None
            r["conv_loose"] = round(loose[name] / prev_l, 6) if prev_l else None
        else:
            r["conv_strict"] = 1.0
            r["churn_strict"] = 0.0
            r["conv_loose"] = 1.0
        r["overall_conv_strict"] = round(strict[name] / base, 6) if base else None
        prev_s, prev_l = strict[name], loose[name]
        rows.append(r)
    out = pd.DataFrame(rows)
    save(out, "agg_funnel_overall")
    log(f"    [漏斗] 严格口径 浏览 {strict['浏览']:,} → 加购 {strict['加购']:,} "
        f"→ 下单 {strict['下单']:,}；整体转化 {out['overall_conv_strict'].iloc[-1]:.2%}")

    # 包含关系核验（用于报告中说明为何需要严格口径）
    check = pd.DataFrame([
        {"关系": "浏览 ⊆ 加购", "成立": bool(len(s_view - s_cart) == 0),
         "反例数": len(s_view - s_cart)},
        {"关系": "下单 ⊆ 加购", "成立": bool(len(s_order - s_cart) == 0),
         "反例数": len(s_order - s_cart)},
        {"关系": "加购 ⊆ 浏览", "成立": bool(len(s_cart - s_view) == 0),
         "反例数": len(s_cart - s_view)},
        {"关系": "下单 ⊆ 浏览", "成立": bool(len(s_order - s_view) == 0),
         "反例数": len(s_order - s_view)},
    ])
    save(check, "funnel_containment_check")

def agg_funnel_by_type(d):
    a = d['action']
    g = a.groupby(["type", "type_label"]).agg(
        pv = ("user_id", "size"), uv = ("user_id", "nunique")
    ).reset_index().sort_values("pv", ascending=False)
    g["pv_share"] = round(g["pv"] / g["pv"].sum(), 4)
    g["pv_per_user"] = round(g["pv"] / g["uv"], 4)
    save(g, "agg_funnel_by_type")

def agg_funnel_by_day(d):
    a = d['action']
    f = a[a['type'].isin(CFG.FUNNEL_ORDER)]
    piv = f.pivot_table(index='dt', columns='type', values='user_id', aggfunc='nunique')
    piv = piv.reindex(columns=CFG.FUNNEL_ORDER).fillna(0).astype(int)
    piv.columns = ['浏览_uv', '加购_uv', '下单_uv']
    out = piv.reset_index()
    out['加购率'] = round(out['加购_uv'] / out['浏览_uv'].replace(0, np.nan), 4)
    out['下单率'] = round(out['下单_uv'] / out['浏览_uv'].replace(0, np.nan), 4)
    out['weekday'] = out['dt'].dt.weekday
    save(out, 'agg_funnel_by_day')

# ================================================================ 3. 用户维度漏斗
def _funnel_by(a: pd.DataFrame, key: str, key_name: str) -> pd.DataFrame:
    """
    按 key 分组计算严格漏斗（嵌套交集），与 agg_funnel_overall 的严格口径保持一致。
    先按 (key, user) 去重得到"用户在组内的行为集合"，再用集合包含关系算嵌套 UV。
    """
    f = a[a["type"].isin(CFG.FUNNEL_ORDER)][[key, "user_id", "type"]].dropna(subset=[key])
    # 每组每个用户的行为类型集合
    g = f.drop_duplicates().groupby([key, "user_id"])["type"].apply(set).reset_index(name="types")

    rows = []
    for kv, sub in g.groupby(key):
        t_series = sub["types"]
        v = int(t_series.apply(lambda s: T_VIEW in s).sum())
        vc = int(t_series.apply(lambda s: T_VIEW in s and T_CART in s).sum())
        vco = int(t_series.apply(lambda s: T_VIEW in s and T_CART in s and T_ORDER in s).sum())
        rows.append({key_name: kv, "浏览_uv": v, "加购_uv": vc, "下单_uv": vco})
    out = pd.DataFrame(rows)
    out["加购率"] = (out["加购_uv"] / out["浏览_uv"].replace(0, np.nan)).round(4)
    out["下单率"] = (out["下单_uv"] / out["浏览_uv"].replace(0, np.nan)).round(4)
    out["加购到下单率"] = (out["下单_uv"] / out["加购_uv"].replace(0, np.nan)).round(4)
    out["用户份额"] = (out["浏览_uv"] / out["浏览_uv"].sum()).round(4)
    return out.sort_values("浏览_uv", ascending=False)


def agg_user_funnels(d: dict) -> None:
    a = d["action"]
    u = d["user"]
    au = a.merge(
        u[["user_id", "user_lv_cd", "lv_label", "sex", "sex_label",
           "age", "age_label", "city_level", "city_level_label"]],
        on="user_id", how="left",
    )
    # user 字段：['user_id', 'age', 'sex', 'user_reg_tm', 'user_lv_cd', 'city_level',
    #   'province', 'city', 'county', 'user_reg_dt', 'reg_year', 'sex_label',
    #   'age_label', 'lv_label', 'city_level_label', 'province_code']
    log(f"  [漏斗] 行为表关联画像后 {len(au):,} 行")

    save(_funnel_by(au, "lv_label", "用户等级"), "agg_user_funnel_by_level")
    save(_funnel_by(au, "sex_label", "性别"), "agg_user_funnel_by_sex")
    save(_funnel_by(au, "age_label", "年龄段"), "agg_user_funnel_by_age")
    save(_funnel_by(au, "city_level_label", "城市等级"), "agg_user_funnel_by_city")


def agg_user_activity(d):
    a = d['action']
    a_cnt = a.groupby('user_id').size()
    dec = pd.qcut(a_cnt, 10, duplicates='drop')
    out = pd.DataFrame({'act_cnt': a_cnt, 'decile': dec}).groupby('decile').agg(
        用户数=('act_cnt', 'size'), 行为量=('act_cnt', 'sum'),
        行为量最小=('act_cnt', 'min'), 行为量最大=('act_cnt', 'max'),
        行为量均值=('act_cnt', 'mean')
    ).reset_index()
    out['行为量占比'] = round(out['行为量'] / out['行为量'].sum(), 6)
    out['行为量均值'] = round(out['行为量均值'], 4)
    save(out, 'agg_user_activity')
    with open(OUT/'user_activity_quantiles.json', 'w', encoding='utf-8') as f:
        json.dump({
            'p50': float(a_cnt.median()),
            'p90': float(a_cnt.quantile(0.9)),
            'p99': float(a_cnt.quantile(0.99)),
            'max': float(a_cnt.max()),
            'min': float(a_cnt.min()),
            'mean': round(float(a_cnt.mean()),2),
            'top10pct_act_share': round(float(a_cnt.nlargest(int(len(a_cnt)*0.1)).sum() / a_cnt.sum()), 6),
        }, f, ensure_ascii=False, indent=2)

# ================================================================ 4. 商品/店铺
def agg_product_shop(d: dict) -> None:
    a = d["action"]
    p = d["product"]
    s = d["shop"]

    # SKU 级行为聚合 -> 挂上品类/品牌/店铺
    sku_agg = a.groupby('sku_id').agg(
        行为量=("user_id", "size"),
        用户数=("user_id", "nunique")
    )
    #  action 中的 user_id , 在 action.sku_id = 4 中的 user_id 都存在
    sku_agg["下单用户数"] = a.loc[a["type"] == T_ORDER].groupby("sku_id")["user_id"].nunique()
    sku_agg["下单行为数"] = a.loc[a["type"] == T_ORDER].groupby("sku_id").size()

    sp = p.merge(sku_agg, on='sku_id', how='left')

    # 品类
    cate = sp.groupby('cate_code', dropna=False).agg(
        SKU数=("sku_id", "nunique"),
        行为量=("行为量", "sum"),
        下单行为数=("下单行为数", "sum"),
        下单用户数=("下单用户数", "sum")).reset_index()
    cate["行为量份额"] = (cate["行为量"] / cate["行为量"].sum()).round(6)
    cate["每SKU行为量"] = (cate["行为量"] / cate["SKU数"].replace(0, np.nan)).round(2)
    # 品类好评率
    cr = d["comment"].merge(p[["sku_id", "cate_code"]], on="sku_id", how="left")
    cg = cr.groupby("cate_code").agg(comments=("comments", "sum"), good=("good_comments", "sum"),
                                     bad=("bad_comments", "sum")).reset_index()
    cg["好评率"] = (cg["good"] / cg["comments"].replace(0, np.nan)).round(6)
    cg["差评率"] = (cg["bad"] / cg["comments"].replace(0, np.nan)).round(6)
    cate = cate.merge(cg[["cate_code", "好评率", "差评率", "comments"]], on="cate_code", how="left")
    save(cate.sort_values("行为量", ascending=False), "agg_cate")

    # 品牌 TOP50
    brand = sp.groupby("brand").agg(
        SKU数=("sku_id", "nunique"), 行为量=("行为量", "sum"),
        下单行为数=("下单行为数", "sum"),
        下单用户数=("下单用户数", "sum")
    ).reset_index()
    brand["行为量份额"] = (brand["行为量"] / brand["行为量"].sum()).round(6)
    brand["每SKU行为量"] = (brand["行为量"] / brand["SKU数"].replace(0, np.nan)).round(2)
    save(brand.sort_values("行为量", ascending=False).head(50), "agg_brand_top50")

    # 店铺
    sh = sp.groupby("shop_id").agg(
        SKU数=("sku_id", "nunique"), 行为量=("行为量", "sum"),
        下单行为数=("下单行为数", "sum"),
        下单用户数=("下单用户数", "sum")
    ).reset_index()
    sh = sh.merge(s[["shop_id", "fans_num", "vip_num", "shop_score", "vip_per_fans", "cate_code"]],
                  on="shop_id", how="left")
    sh["行为量份额"] = (sh["行为量"] / sh["行为量"].sum()).round(6)
    sh["每SKU行为量"] = (sh["行为量"] / sh["SKU数"].replace(0, np.nan)).round(2)
    save(sh.sort_values("行为量", ascending=False).head(100), "agg_shop_top100")

    # 店铺评分与经营相关性
    valid = sh[sh["shop_score"].notna()].copy()
    corr = {}
    for c in ["fans_num", "vip_num", "行为量", "下单行为数", "SKU数"]:
        if valid[c].notna().sum() > 2:
            corr[c] = round(float(valid['shop_score'].corr(valid[c])), 4)
    with open(OUT / "shop_score_corr.json", "w", encoding="utf-8") as f:
        json.dump({"n_valid_shop_score": len(valid), "corr_with_shop_score": corr}, f, ensure_ascii=False, indent=2)

# ================================================================ 5. 时间维度
def agg_time(d: dict) -> None:
    a = d["action"]
    daily = a.groupby("dt").agg(
        行为量=("user_id", "size"), 活跃用户数=("user_id", "nunique"),
    ).reset_index()
    daily = daily.merge(
        a.loc[a["type"] == T_ORDER].groupby("dt").agg(下单行为数=("user_id", "size"),
                                               下单用户数=("user_id", "nunique")).reset_index(),
        on="dt", how="left",
    ).fillna(0)
    daily["人均行为"] = (daily["行为量"] / daily["活跃用户数"]).round(3)
    daily["下单转化率"] = (daily["下单用户数"] / daily["活跃用户数"]).round(6)
    daily["行为占比"] = (daily["行为量"] / daily["行为量"].sum()).round(6)
    daily["weekday"] = daily["dt"].dt.weekday
    daily["is_weekend"] = daily["weekday"] >= 5
    save(daily, "agg_time_daily")

    hourly = a.groupby("hour").agg(行为量=("user_id", "size"),
                                   活跃用户数=("user_id", "nunique")).reset_index()
    hourly = hourly.merge(
        a.loc[a["type"] == T_ORDER].groupby("hour").agg(下单行为数=("user_id", "size"),下单用户数=('user_id', 'nunique')).reset_index(),
        on="hour", how="left",
    ).fillna(0)
    hourly["人均行为"] = (hourly["行为量"] / hourly["活跃用户数"]).round(3)
    hourly["下单转化率"] = (hourly["下单用户数"] / hourly["活跃用户数"]).round(6)
    hourly["行为占比"] = (hourly["行为量"] / hourly["行为量"].sum()).round(6)
    save(hourly, "agg_time_hourly")

    wd = a.groupby("weekday").agg(行为量=("user_id", "size"),
                                  活跃用户数=("user_id", "nunique")).reset_index()
    wd = wd.merge(a.loc[a["type"] == T_ORDER].groupby("weekday").agg(下单行为数=("user_id", "size"),下单用户数=('user_id', 'nunique')).reset_index(),
                  on="weekday", how="left").fillna(0)
    wd["人均行为"] = (wd["行为量"] / wd["活跃用户数"]).round(3)
    wd["下单转化率"] = (wd["下单用户数"] / wd["活跃用户数"]).round(6)
    wd["行为占比"] = (wd["行为量"] / wd["行为量"].sum()).round(6)
    wd["星期"] = wd["weekday"].map({0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"})
    save(wd, "agg_time_weekday")

    share = {
        "weekend_act_share": round(float(a.loc[a["is_weekend"], "user_id"].size / len(a)), 6),
        "peak_hour": int(hourly.loc[hourly["行为量"].idxmax(), "hour"]),
        "peak_day": str(daily.loc[daily["行为量"].idxmax(), "dt"].date()),
        "trough_day": str(daily.loc[daily["行为量"].idxmin(), "dt"].date()),
    }
    with open(OUT / "time_summary.json", "w", encoding="utf-8") as f:
        json.dump(share, f, ensure_ascii=False, indent=2)


# ================================================================ 6. 交叉矩阵
def agg_cross(d: dict) -> None:
    a = d["action"]
    p = d["product"]
    u = d["user"]

    orders = a[a["type"] == T_ORDER][["user_id", "sku_id"]]
    o = orders.merge(p[["sku_id", "cate_code"]], on="sku_id", how="left")
    o = o.merge(u[["user_id", "lv_label", "city_level_label"]], on="user_id", how="left")

    m1 = o.groupby(["cate_code", "lv_label"])["user_id"].nunique().reset_index(name="下单用户数")
    save(m1, "agg_cate_userlevel")

    m2 = (o.groupby(["cate_code", "city_level_label"])["user_id"].nunique()
          .reset_index(name="下单用户数"))
    save(m2, "agg_cate_citylevel")

# ================================================================ 主流程
def main():
    log("=" * 60)
    log("京东数据 · 指标与分组聚合")
    log("=" * 60)

    d = load()
    write_metric_dictionary()
    log("[聚合] 总体指标")
    agg_overall(d)
    log("[聚合] 漏斗")
    agg_funnel_overall(d)
    agg_funnel_by_type(d)
    agg_funnel_by_day(d)
    log("[聚合] 用户维度")
    agg_user_funnels(d)
    agg_user_activity(d)
    log("[聚合] 商品/店铺")
    agg_product_shop(d)
    log("[聚合] 时间维度")
    agg_time(d)
    log("[聚合] 交叉矩阵")
    agg_cross(d)

    log("\n===== 聚合完成 =====")
    log(f"产出目录：{OUT}")

if __name__ == "__main__":
    main()