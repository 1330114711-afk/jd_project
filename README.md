# 京东电商平台用户消费数据分析

> 基于京东 JData 公开数据集的端到端用户消费行为分析项目：
> **3,721 万条行为日志 → 数据体检 → 清洗标准化 → 指标聚合 → 统计检验 → 可视化 → SQLite → 交互式看板 → 洞察报告**，
> 一条命令可完整复现。

---

## 项目速览

| 维度 | 说明 |
|---|---|
| **数据规模** | 行为 3,721 万条（1.6 GB CSV）/ 用户 104.9 万 / 商品 35.3 万 / 店铺 1.04 万 / 评论 177.4 万条 |
| **观测窗口** | 2018-02-01 ~ 2018-04-15（74 天） |
| **技术栈** | Python 3.13 · pandas · NumPy · SciPy · Matplotlib · SQLite · Streamlit · Parquet |
| **分析方法** | 漏斗分析 · 时间序列（移动平均/环比）· 异常检测（z-score/IQR/MAD 三法交叉）· 假设检验（Welch t / 卡方）· 效应量（Cohen's d / Cramér's V）· 用户分位分层 |
| **交付产出** | 4 份报告 · 40+ 结果表 · 8 张图表 · SQLite 库（29 表）· 8 页交互看板 · 一键流水线 |
| **核心结论** | 整体转化率 29.47% · 复购率 41.75% · 春节效应 d=−1.53（大）· 顶部 10% 用户贡献 54% 行为量 |

---

## 核心发现（TL;DR）

1. **整体转化率 29.47%**（严格嵌套口径）—— 浏览 132.9 万 → 下单 39.2 万人
2. **复购率 41.75%**，下单用户人均下单 2.08 次
3. **春节是全年最大异常源** —— 行为量旬环比 −52.6%，效应量 Cohen's d = −1.53（大）
4. **不存在显著周末效应** —— p 不显著，d=0.159（可忽略），可简化运营日历
5. **顶部 10% 用户贡献 53.96% 行为量**，人均行为 128 次 vs 底部 1.3 次，差距 99 倍
6. **晚间 20-23 点是黄金时段**，22 点达峰（7.43%）；上午 10 点为次峰
7. **C07 品类一品类独大** —— 占行为量 31.25%，SKU 数仅占 20.5%
8. **好评率 97.88%**，无质量塌陷品类（各品类差评率 1.0%~1.3%）

---

## 一键运行

```bash
# 1) 安装依赖
pip install -r requirements.txt

# 2) 全流程复现（raw → report，约 40 分钟，主要耗时在 1.6GB 行为表）
python scripts/run_pipeline.py

# 3) 启动交互式看板
streamlit run app/dashboard.py
```

### 流水线阶段

| 阶段 | 内容 | 脚本 | 主要产出 |
|---|---|---|---|
| S1 | 数据体检 | `src/01_data_health_check.py` | `health_report.json` 等 4 个 |
| S2 | 清洗标准化 | `src/02_cleaning.py` | `data/processed/*.parquet`（5 表） |
| S3 | 指标与分组聚合 | `src/03_metrics_aggregation.py` | `agg_*.csv`（13 个） |
| S4 | 时间序列 + NumPy 统计 | `src/04_timeseries_stats.py` | `ts_*.csv`、`anomaly_*.csv`、`thresholds.json` |
| S5 | 统计检验 | `src/05_stat_tests.py` | `stat_tests.csv`、`stat_group_desc.csv` |
| S6 | Matplotlib 可视化 | `src/06_visualize.py` | `outputs/figures/*.png`（8 张） |
| S7 | 数据质量门禁 | `src/09_quality_report.py` | `quality_rules.csv`、`quality_summary.json` |
| S8 | 入库 SQLite | `src/07_sqlite_load.py` | `outputs/results.db`（29 表） |
| S9 | SQL 分析查询 | `src/08_sql_queries.py` | `sql_q01~q10_*.csv`、`sql_report.md` |

### 常用命令

```bash
python scripts/run_pipeline.py --list          # 查看所有阶段
python scripts/run_pipeline.py --fast          # 快速模式（清洗抽样 500 万行，仅验证流程）
python scripts/run_pipeline.py --from S3       # 从指定阶段续跑（复用已有产出）
python scripts/run_pipeline.py --only S6 S7    # 只跑指定阶段
python src/08_sql_queries.py                   # 单独执行 SQL 分析
```

> **重复运行安全**：所有脚本幂等，产出覆盖写入，不污染 `data/raw/`（原始数据只读）。

---

## 看板截图

启动 `streamlit run app/dashboard.py` 后包含 8 个页面：

| 页面 | 内容 |
|---|---|
| 📊 总览 | 核心指标卡 · 严格口径漏斗 · 日趋势 · 图表总览 |
| 🔍 异常与趋势 | 三法检出对比 · 高置信异常明细 · z-score 控制图 |
| 👥 用户画像 | 等级/性别/年龄/城市 漏斗 · 活跃度分位 |
| 🛍 商品店铺 | 品类 TOP20 · 店铺 TOP20 · 品牌 TOP20 |
| ⏱ 时间节律 | 小时分布 · 星期分布 · 旬/周趋势 |
| 🧪 统计检验 | 检验结论速览 · 分组描述明细 |
| 🚦 数据质量 | 质量分 · 规则通过情况 · 未通过项 |
| 🗃 SQL 查询台 | 预设查询 · 自定义 SQL · 结果下载 |


![总览](docs/screenshots/01_overview.png)

![异常与趋势](docs/screenshots/02_anomaly.png)

### 关键图表

| 图 | 说明 |
|---|---|
| `fig01_funnel.png` | 用户行为漏斗（含转化率/流失率标注） |
| `fig02_daily_trend.png` | 日趋势 + 7 日移动平均 + 异常点 + 春节阴影 |
| `fig03_anomaly_zscore.png` | z-score 控制图（±2σ/±3σ 阈值带） |
| `fig04_hourly_heatmap.png` | 星期 × 小时 行为热力图 |
| `fig05_user_level.png` | 用户等级规模与下单率 |
| `fig06_cate_top.png` | 品类 TOP15 行为量 |
| `fig07_stats_box.png` | 各指标箱线图（标注 IQR 离群） |
| `fig08_period_trend.png` | 旬分段趋势（行为量 + 日均下单用户双轴） |

---

## 项目结构

```
jd_project/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/                    # 原始数据（只读，5 个 CSV）
│   └── processed/              # 清洗后 parquet（5 表）
├── src/                        # 分析脚本
│   ├── config_codes.py         # 编码映射与清洗口径配置（含置信度标注）
│   ├── 01_data_health_check.py # 数据体检
│   ├── 02_cleaning.py          # 清洗标准化（分块处理 1.6G）
│   ├── 03_metrics_aggregation.py # 指标与分组聚合
│   ├── 04_timeseries_stats.py  # 时间序列 + NumPy 统计 + 异常检测
│   ├── 05_stat_tests.py        # 统计检验与效应量
│   ├── 06_visualize.py         # Matplotlib 可视化
│   ├── 07_sqlite_load.py       # 评估结果入库 SQLite
│   ├── 08_sql_queries.py       # SQL 分析查询
│   └── 09_quality_report.py    # 数据质量门禁
├── scripts/
│   └── run_pipeline.py         # 一键流水线（raw → report）
├── app/
│   └── dashboard.py            # Streamlit 评估看板
├── docs/
│   └── data_dictionary.md      # 字段与口径字典（含待核实清单）
└── outputs/
    ├── report_data_health.md   # ① 数据体检报告
    ├── report_cleaning.md      # ② 清洗标准化报告
    ├── report_evaluation.md    # ③ 评估分析报告（主报告）
    ├── sql_report.md           # ④ SQL 查询结果汇总
    ├── results.db              # SQLite 数据库（29 表）
    ├── tables/                 # 40+ 结果表 CSV
    ├── figures/                # 8 张图表 PNG
    └── logs/                   # 流水线日志与摘要
```

---

## 技术亮点

### 1. 大表分块处理
1.6 GB / 3,721 万行行为表用 `pandas.read_csv(chunksize=1_000_000, dtype=str)` 分块处理，
分片写 Parquet 后合并，峰值内存可控，全程约 25 分钟。

### 2. 异常检测三法交叉投票
单一方法在偏态指标上会漏检。本项目并行运行三种方法：

| 方法 | 阈值 | 特点 |
|---|---|---|
| z-score | \|z\|>2 warn / >3 crit | 对极值敏感，最保守 |
| IQR (Tukey) | 超出 Q1−1.5IQR ~ Q3+1.5IQR | 对偏态较稳健，最宽松 |
| MAD (modified z) | \|mz\|>3.5 | 用中位数，最稳健 |

**≥2 种方法命中才判为高置信异常**。实测在下单行为数上，z-score 检出 6 天而 MAD 检出 10 天 —— 三法交叉显著降低了漏检率。

### 3. 显著性 + 效应量双报告
86.7 万样本下卡方检验对微小差异也会判显著。本项目强制同时报告 Cohen's d / Cramér's V，
避免"p<0.05 就宣布有差异"的误读：
- 性别 × 下单：p 显著，但 V=0.063（可忽略）→ **不应向业务方宣称存在性别差异**
- 春节效应：d=−1.53（大）→ **唯一值得行动的因素**

### 4. 漏斗口径的自洽性校验
发现 `浏览 ⊆ 加购`（0 反例）但有 27.98 万用户"只加购不浏览"，
导致宽松口径算出 **121% 的不可能转化率**。
为此并列输出两种口径，并在 `funnel_containment_check` 中记录包含关系核验结果，
评估以**严格嵌套口径**（29.47%）为准。

### 5. 编码字段的置信度管理
`config_codes.py` 中每个映射标注 `official` / `inferred` / `unknown`，
未核实的映射禁止直接用于对外结论，从机制上防止口径漂移。

---

## 数据质量

质量门禁 **91.67/100**，等级 **WARN**（12 条规则，11 条通过，0 条 error 级失败）。

| 规则 | 结果 |
|---|---|
| 主键唯一 / 关键字段非空 / 类型域 / 时间域 | ✅ 全部通过（0 违规） |
| 评论勾稽 `good+bad ≤ comments` | ✅ 8,537,575 条零违规 |
| 店铺评分域 / 粉丝会员非负 | ✅ 占位值已转空 2,446 条 |
| **用户画像覆盖率** | ⚠️ 65.28%（阈值 90%）—— 34.72% 行为无法关联画像 |

详见 `outputs/report_evaluation.md` 第一节。

---

## 已知局限

| 局限 | 影响 | 处理 |
|---|---|---|
| 34.72% 行为无用户画像 | 画像分析样本收缩至 104.9 万 | 报告中显式标注覆盖率 |
| 无金额字段 | GMV / 客单价 / ARPU 不可算 | 改用行为量级指标 |
| `浏览` 行为采集不完整 | 漏斗首环节失真 | 采用严格嵌套口径并披露 |
| `cate`/`province`/`brand` 编码未映射 | 无法给出中文维度名 | 仅用编码做相对排名 |
| `age` 为年龄段编码（1~6） | 不可作连续变量 | 标注为编码 |
| 观测窗口仅 74 天 | 无法做季节性趋势 | 结论限定窗口内 |

---

## 环境要求

- Python ≥ 3.10（开发环境 3.13.12）
- 内存建议 ≥ 8 GB（处理 1.6 GB 行为表）
- 磁盘建议 ≥ 6 GB（原始 1.6 GB + 中间 Parquet 约 1.1 GB）

```bash
pip install -r requirements.txt
```

---

## 说明

- 数据来源：京东 JData 公开数据集（脱敏样例），仅用于数据分析学习与方法验证。
- 涉及用户隐私的字段（`user_id` 等）仅在本地方便关联使用，不对外披露。
- 所有编码映射的置信度标注见 `docs/data_dictionary.md`，未核实项禁止用于对外结论。
