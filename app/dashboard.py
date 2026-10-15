"""
app/dashboard.py — 京东用户消费数据分析 · Streamlit 评估看板

前置
    outputs/results.db（由 src/07_sqlite_load.py 产出）
    outputs/figures/*.png（由 src/06_visualize.py 产出，可选）

运行
    streamlit run app/dashboard.py
    或指定端口：streamlit run app/dashboard.py --server.port 8501

页面
    📊 总览        核心指标卡 + 严格口径漏斗 + 日趋势
    🔍 异常与趋势  z-score 控制图 + 异常样本表
    👥 用户画像    等级 / 性别 / 年龄 / 城市 漏斗与下单率
    🛍 商品店铺    品类排行 + 店铺 TOP
    ⏱ 时间节律     小时 / 星期 分布
    🧪 统计检验    检验结论表 + 分组描述
    🚦 数据质量    质量规则通过情况 + 未通过项
    🗃 SQL 查询    直接执行 SQL 并下载结果

说明
    看板只读 results.db，不触发任何计算，秒级打开。
    所有图表优先读 DB，缺失时自动降级隐藏，不会报错中断。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "outputs" / "results.db"
FIG = ROOT / "outputs" / "figures"

st.set_page_config(page_title="京东用户消费数据分析 · 评估看板",
                   page_icon="📊", layout="wide")

# ---------------------------------------------------------------- 数据访问
@st.cache_resource
def get_conn() -> sqlite3.Connection:
    if not DB.exists():
        st.error(f"未找到数据库：{DB}\n\n请先运行 `python src/run_pipeline.py` 或 `python src/07_sqlite_load.py`")
        st.stop()
    return sqlite3.connect(DB, check_same_thread=False)


@st.cache_data(ttl=300)
def q(sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql_query(sql, get_conn())
    except Exception as e:
        st.warning(f"查询失败：{type(e).__name__}: {e}")
        return pd.DataFrame()


def table_exists(name: str) -> bool:
    r = q(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}'")
    return not r.empty


def kv(table: str, key_col: str, val_col: str) -> dict:
    """把 metric/value 两列式表读成 dict。"""
    if not table_exists(table):
        return {}
    d = q(f'SELECT "{key_col}" k, "{val_col}" v FROM {table}')
    out = {}
    for _, r in d.iterrows():
        try:
            out[str(r["k"])] = float(r["v"])
        except (TypeError, ValueError):
            out[str(r["k"])] = r["v"]
    return out


# ---------------------------------------------------------------- 侧边栏
st.sidebar.title("📊 京东消费数据分析")
st.sidebar.caption("数据窗口 2018-02-01 ~ 2018-04-15（74 天）")
page = st.sidebar.radio("导航", [
    "📊 总览", "🔍 异常与趋势", "👥 用户画像", "🛍 商品店铺",
    "⏱ 时间节律", "🧪 统计检验", "🚦 数据质量", "🗃 SQL 查询",
])
st.sidebar.divider()
st.sidebar.caption("数据源 `outputs/results.db`")
if st.sidebar.button("🔄 清除缓存"):
    st.cache_data.clear()
    st.rerun()


# ================================================================ 总览
def page_overview() -> None:
    st.header("核心指标总览")
    o = kv("agg_overall", "index", "c_0")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("行为记录总数", f"{int(o.get('total_action_rows', 0)):,}")
    c2.metric("活跃用户数", f"{int(o.get('total_users_active', 0)):,}")
    c3.metric("商品 SKU 数", f"{int(o.get('total_skus', 0)):,}")
    c4.metric("店铺数", f"{int(o.get('total_shop', 0)):,}")

    c5, c6, c7, c8 = st.columns(4)
    conv = o.get("overall_conv_rate_strict")
    c5.metric("整体转化率（严格）", f"{conv:.2%}" if isinstance(conv, float) else "—")
    rep = o.get("repurchase_rate")
    c6.metric("复购率", f"{rep:.2%}" if isinstance(rep, float) else "—")
    gr = o.get("good_rate")
    c7.metric("好评率", f"{gr:.2%}" if isinstance(gr, float) else "—")
    cov = o.get("user_profile_coverage")
    c8.metric("画像覆盖率", f"{cov:.2%}" if isinstance(cov, float) else "—")

    st.divider()
    left, right = st.columns([1, 1])

    with left:
        st.subheader("用户行为漏斗（严格嵌套口径）")
        f = q("""
            SELECT stage, uv_strict, uv_loose, conv_strict, overall_conv_strict
            FROM agg_funnel_overall ORDER BY stage_order
        """)
        if not f.empty:
            show = f.rename(columns={
                "stage": "环节", "uv_strict": "严格UV", "uv_loose": "宽松UV(对照)",
                "conv_strict": "环节转化率", "overall_conv_strict": "整体转化率"})
            st.dataframe(show, width="stretch", hide_index=True)
            st.caption("严格口径 = 嵌套交集（浏览→浏览∩加购→浏览∩加购∩下单），转化率 ≤100%；"
                       "宽松口径各环节独立去重，本数据下加购 UV > 浏览 UV，故评估以严格口径为准。")

    with right:
        st.subheader("行为构成")
        t = q("""
            SELECT type_label, pv AS 行为量, uv AS 独立用户, pv_share AS 占比
            FROM agg_funnel_by_type ORDER BY pv DESC
        """)
        if not t.empty:
            t["占比"] = (t["占比"] * 100).round(2).astype(str) + "%"
            st.dataframe(t, width="stretch", hide_index=True)

    st.divider()
    st.subheader("日行为量趋势")
    d = q("SELECT dt, action_cnt, active_users, order_cnt, action_ma7 "
          "FROM ts_daily_trend ORDER BY dt")
    if not d.empty:
        d["dt"] = pd.to_datetime(d["dt"])
        d = d.set_index("dt")
        st.line_chart(d[["action_cnt", "action_ma7"]], height=320)
        st.caption("蓝线为日行为量，橙线为 7 日移动平均。")

    st.divider()
    st.subheader("核心图表")
    figs = [("fig01_funnel.png", "漏斗"), ("fig02_daily_trend.png", "日趋势"),
            ("fig08_period_trend.png", "旬趋势")]
    cols = st.columns(len(figs))
    for col, (fn, cap) in zip(cols, figs):
        p = FIG / fn
        if p.exists():
            col.image(str(p), caption=cap, width="stretch")


# ================================================================ 异常与趋势
def page_anomaly() -> None:
    st.header("异常检测与趋势诊断")

    o = kv("agg_overall", "index", "c_0")
    s = kv("stats_summary", "指标", "mean")
    st.caption("检测方法：z-score（|z|>2 warn，>3 crit）+ IQR（Tukey 1.5）+ MAD（modified z>3.5）；"
               "≥2 种方法命中记为高置信异常。")

    st.subheader("各方法检出对比")
    m = q("SELECT * FROM anomaly_by_method")
    if not m.empty:
        st.dataframe(m, width="stretch", hide_index=True)

    st.divider()
    st.subheader("高置信异常日明细")
    a = q("""
        SELECT metric AS 指标, dt AS 日期, metric_value AS 指标值,
               z_score, modified_z, flag_zscore, flag_iqr, flag_mad,
               anomaly_votes AS 命中方法数, direction AS 方向
        FROM anomaly_samples ORDER BY metric, dt
    """)
    if not a.empty:
        metric = st.selectbox("指标筛选", ["全部"] + sorted(a["指标"].unique().tolist()))
        view = a if metric == "全部" else a[a["指标"] == metric]
        st.dataframe(view, width="stretch", hide_index=True)
        st.caption(f"共 {len(view)} 条高置信异常。")
    else:
        st.info("无高置信异常记录。")

    st.divider()
    st.subheader("z-score 控制图")
    p = FIG / "fig03_anomaly_zscore.png"
    if p.exists():
        st.image(str(p), width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("箱线图（IQR 离群）")
        p = FIG / "fig07_stats_box.png"
        if p.exists():
            st.image(str(p), width="stretch")
    with col2:
        st.subheader("统计指标汇总")
        sm = q("SELECT metric, n, mean, std_pop, cv, p05, p50, p95, skew FROM stats_summary")
        if not sm.empty:
            st.dataframe(sm, width="stretch", hide_index=True)


# ================================================================ 用户画像
def page_user() -> None:
    st.header("用户画像与分层")

    dims = {
        "用户等级": ("agg_user_funnel_by_level", "user_level"),
        "性别": ("agg_user_funnel_by_sex", "sex"),
        "年龄段": ("agg_user_funnel_by_age", "age_band"),
        "城市等级": ("agg_user_funnel_by_city", "city_level"),
    }
    tabs = st.tabs(list(dims.keys()))
    for tab, (label, (tbl, col)) in zip(tabs, dims.items()):
        with tab:
            df = q(f"""
                SELECT {col} AS 分组, uv_view AS 浏览UV, uv_cart AS 加购UV, uv_order AS 下单UV,
                       ROUND(order_rate*100,2) AS 下单率pct, ROUND(user_share*100,2) AS 用户份额pct
                FROM {tbl} ORDER BY uv_view DESC
            """)
            if df.empty:
                st.info("无数据")
                continue
            st.dataframe(df, width="stretch", hide_index=True)
            if label == "用户等级":
                import altair as alt
                ch = alt.Chart(df).mark_bar().encode(
                    x=alt.X("分组:N", sort="-y", title="用户等级"),
                    y=alt.Y("下单率pct:Q", title="下单率 (%)"),
                    tooltip=["分组", "下单率pct", "浏览UV"],
                ).properties(height=280, title="各等级下单率")
                st.altair_chart(ch, width="stretch")

    st.divider()
    st.subheader("用户活跃度分位（行为次数）")
    act = q("SELECT * FROM agg_user_activity")
    if not act.empty:
        st.dataframe(act, width="stretch", hide_index=True)
        st.caption("高频用户贡献绝大部分行为量；长尾用户规模大但单量低。")

    col1, col2 = st.columns(2)
    with col1:
        p = FIG / "fig05_user_level.png"
        if p.exists():
            st.image(str(p), width="stretch")
    with col2:
        p = FIG / "fig04_hourly_heatmap.png"
        if p.exists():
            st.image(str(p), caption="星期 × 小时 热力图", width="stretch")


# ================================================================ 商品店铺
def page_product() -> None:
    st.header("商品与店铺")

    st.subheader("品类排行（TOP20）")
    c = q("""
        SELECT cate_code, sku_cnt, action_cnt, order_users,
               ROUND(action_share*100,3) AS 行为份额pct,
               ROUND(good_rate*100,2) AS 好评率pct, ROUND(bad_rate*100,2) AS 差评率pct
        FROM agg_cate ORDER BY action_cnt DESC LIMIT 20
    """)
    if not c.empty:
        st.dataframe(c, width="stretch", hide_index=True)
        st.caption("品类编码未映射为中文名，见 docs/data_dictionary.md。")

    st.divider()
    st.subheader("店铺 TOP20")
    sh = q("""
        SELECT shop_id, sku_cnt, action_cnt, order_users, fans_num, vip_num,
               ROUND(vip_per_fans*100,2) AS 粉丝转会员pct, ROUND(shop_score,2) AS 评分
        FROM agg_shop_top100 ORDER BY action_cnt DESC LIMIT 20
    """)
    if not sh.empty:
        st.dataframe(sh, width="stretch", hide_index=True)
        st.caption("评分空值表示原值为 -1/0 的无效占位，已排除。")

    st.divider()
    st.subheader("品牌 TOP20")
    b = q("SELECT * FROM agg_brand_top50 ORDER BY action_cnt DESC LIMIT 20")
    if not b.empty:
        st.dataframe(b, width="stretch", hide_index=True)

    p = FIG / "fig06_cate_top.png"
    if p.exists():
        st.image(str(p), width="stretch")


# ================================================================ 时间节律
def page_time() -> None:
    st.header("时间节律")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("小时分布")
        h = q("SELECT hour, action_cnt, active_users, ROUND(action_share*100,3) AS pct FROM agg_time_hourly ORDER BY hour")
        if not h.empty:
            st.bar_chart(h.set_index("hour")["action_cnt"], height=300)
            st.dataframe(h, width="stretch", hide_index=True)
    with col2:
        st.subheader("星期分布")
        w = q("SELECT weekday_name AS 星期, action_cnt, active_users, ROUND(action_share*100,3) AS pct "
              "FROM agg_time_weekday ORDER BY weekday")
        if not w.empty:
            st.bar_chart(w.set_index("星期")["action_cnt"], height=300)
            st.dataframe(w, width="stretch", hide_index=True)

    st.divider()
    st.subheader("旬分段趋势")
    pr = q("SELECT * FROM ts_period")
    if not pr.empty:
        st.dataframe(pr, width="stretch", hide_index=True)

    st.divider()
    st.subheader("周聚合趋势")
    wk = q("SELECT * FROM ts_weekly ORDER BY week_start")
    if not wk.empty:
        st.dataframe(wk, width="stretch", hide_index=True)


# ================================================================ 统计检验
def page_stat() -> None:
    st.header("统计检验")

    st.caption("显著性水平 α=0.05。大样本下 p 值易显著，须结合效应量"
               "（Cohen's d：0.2小/0.5中/0.8大；Cramér's V：0.1弱/0.3中/0.5强）判断实际意义。")

    t = q("SELECT * FROM stat_tests")
    if not t.empty:
        # 只展示核心列，避免太宽
        keep = [c for c in ["test_name", "conclusion", "effect_strength",
                            "p_welch", "p_chi2", "cohen_d", "cramers_v"] if c in t.columns]
        st.dataframe(t[keep], width="stretch", hide_index=True)

        st.subheader("检验结论速览")
        for _, r in t.iterrows():
            concl = str(r.get("conclusion", ""))
            icon = "✅" if concl.startswith("拒绝") else "➖"
            eff = r.get("effect_strength", "")
            st.markdown(f"{icon} **{r['test_name']}** — {concl}　效应量：`{eff}`")

    st.divider()
    st.subheader("分组描述统计（检验输入明细）")
    g = q("SELECT * FROM stat_group_desc")
    if not g.empty:
        st.dataframe(g, width="stretch", hide_index=True)


# ================================================================ 数据质量
def page_quality() -> None:
    st.header("数据质量")

    # quality_summary 为 JSON 文件（非表），直接读取
    import json
    pf = ROOT / "outputs" / "tables" / "quality_summary.json"
    qs = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}

    if qs:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("质量分", f"{qs.get('quality_score', '—')}/100")
        c2.metric("门禁", qs.get("gate", "—"))
        c3.metric("规则总数", qs.get("n_rules", "—"))
        c4.metric("未通过", qs.get("n_failed", "—"))
        st.caption("门禁规则：存在 error 级未通过 → BLOCK；仅 warn 未通过 → WARN；全通过 → PASS。")

    st.divider()
    st.subheader("规则通过情况")
    r = q("SELECT * FROM quality_rules")
    if not r.empty:
        st.dataframe(r, width="stretch", hide_index=True)

    st.divider()
    st.subheader("未通过项")
    i = q("SELECT * FROM quality_issues")
    if not i.empty:
        st.dataframe(i, width="stretch", hide_index=True)
    else:
        st.success("全部规则通过。")


# ================================================================ SQL 查询
def page_sql() -> None:
    st.header("SQL 查询台")
    st.caption("直接对 outputs/results.db 执行只读 SQL，结果可下载。")

    tables = q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    with st.expander("📋 可用数据表"):
        if not tables.empty:
            st.write(", ".join(tables["name"].tolist()))

    presets = {
        "① 大盘指标": 'SELECT "index", c_0 FROM agg_overall LIMIT 30',
        "② 日趋势 Top10": "SELECT dt, action_cnt, active_users FROM ts_daily_trend ORDER BY action_cnt DESC LIMIT 10",
        "③ 异常日": "SELECT metric, dt, metric_value, z_score FROM anomaly_samples ORDER BY ABS(z_score) DESC",
        "④ 等级下单率": "SELECT user_level, uv_view, uv_order, order_rate FROM agg_user_funnel_by_level ORDER BY order_rate DESC",
        "⑤ 品类 TOP10": "SELECT cate_code, action_cnt, order_users, good_rate FROM agg_cate ORDER BY action_cnt DESC LIMIT 10",
        "⑥ 检验结论": "SELECT test_name, conclusion, effect_strength FROM stat_tests",
    }
    pick = st.selectbox("预设查询", list(presets.keys()))
    sql = st.text_area("SQL", value=presets[pick], height=140)

    if st.button("▶ 执行", type="primary"):
        df = q(sql)
        if not df.empty:
            st.success(f"返回 {len(df)} 行")
            st.dataframe(df, width="stretch", hide_index=True)
            st.download_button("⬇ 下载 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                               file_name="query_result.csv", mime="text/csv")
        else:
            st.info("查询无结果或执行失败（仅允许只读查询）。")


# ================================================================ 路由
ROUTES = {
    "📊 总览": page_overview,
    "🔍 异常与趋势": page_anomaly,
    "👥 用户画像": page_user,
    "🛍 商品店铺": page_product,
    "⏱ 时间节律": page_time,
    "🧪 统计检验": page_stat,
    "🚦 数据质量": page_quality,
    "🗃 SQL 查询": page_sql,
 }
ROUTES[page]()
