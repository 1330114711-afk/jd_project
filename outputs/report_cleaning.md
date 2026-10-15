# 数据清洗与标准化报告

**项目**：京东电商平台用户消费数据分析
**清洗脚本**：`src/02_cleaning.py` + 配置 `src/config_codes.py`
**输入**：`data/raw/*.csv`（5 张原始表，只读）
**输出**：`data/processed/*.parquet`

---

## 一、清洗总览

| 表 | 原始行数 | 清洗后行数 | 变化 | 主要动作 |
|---|---:|---:|---|---|
| `user` | 1,048,575 | 1,048,575 | — | sex 占位值转 NaN（7,700 条）、时间标准化、派生标签 |
| `product` | 352,539 | 352,539 | — | 类型规范、上架时长派生 |
| `shop` | 10,399 | 10,399 | — | shop_score 占位值转 NaN（2,446 条）、vip_per_fans 派生 |
| `comment` | 1,774,233 | 1,774,233 | — | 勾稽校验（0 违规）、好评率/差评率/中评派生 |
| `action` | 37,214,269 | 36,854,867 | **−359,402** | 完全重复行去重、时间解析、宽度派生、关联标记 |

**总量**：行为表去重删除 359,402 条（0.97%），其余表行数不变（清洗是"值级修正"而非"行级过滤"）。

---

## 二、清洗动作明细

逐条记录见 `outputs/tables/cleaning_log.csv`。

### 2.1 占位值 → NaN

占位值伪装成正常取值是本次数据最隐蔽的坑，必须显式排除。

| 表 | 字段 | 占位值 | 条数 | 占比 | 处理 |
|---|---|---|---:|---:|---|
| user | `sex` | `-1` | 7,700 | 0.73% | → NaN |
| shop | `shop_score` | `-1` | 1,767 | 16.99% | → NaN |
| shop | `shop_score` | `0` | 679 | 6.53% | → NaN（疑似未评分） |

**为何要处理**：`shop_score` 的 `-1` 若参与均值计算，会把店铺评分从真实水平拉低；`sex = -1` 若当作"第三种性别"统计则凭空多出一个类别。

### 2.2 时间标准化

| 问题 | 表现 | 处理 |
|---|---|---|
| `.0` 后缀 | `2018-02-04 08:28:15.0` | 正则去尾 `\.0$` |
| 日期格式不统一 | `2018-2-4` 与 `2015-7-2` | 统一解析为 `datetime64`，同时派生规范字符串 |
| 解析容错 | 多形态混排 | `pd.to_datetime(..., format="mixed")` |

派生时间字段（行为表）：`action_dt`（完整时间戳）、`dt`（日期）、`hour`、`weekday`、`is_weekend`。
维度表派生：`user_reg_dt`、`market_dt`、`shop_reg_dt`，以及 `reg_year` / `tenure_days` / `listed_days`、`market_year`。

### 2.3 类型规范

- 各 ID 字段统一为 `int64`
- 编码字段（`type`、`weekday`、`hour` 等）用 `int8` 省内存
- 可空数值（`cate`、`city_level`）用可空整型 `Int8/Int32`
- 布尔标记用 `bool`

### 2.4 派生特征

| 表 | 新增字段 | 含义 |
|---|---|---|
| action | `type_label` | 行为中文名 |
| action | `is_funnel` | 是否属于漏斗环节（浏览/加购/下单） |
| action | `user_has_profile` | 能否关联到 user 表 |
| action | `sku_has_product` | 能否关联到 product 表 |
| user | `sex_label` / `age_label` / `lv_label` / `city_level_label` | 映射标签 |
| user | `tenure_days` | 注册至今（截至 2018-04-15）天数 |
| product | `listed_days` | 上架至今天数 |
| product/shop | `cate_code` | 品类编码可读形式 `C07` |
| shop | `vip_per_fans` | 会员/粉丝转化率 |
| comment | `neutral_comments` | 中评数 = 总数 − 好评 − 差评 |
| comment | `good_rate` / `bad_rate` | 好评率 / 差评率 |

### 2.5 去重

行为表按 `(user_id, sku_id, action_time, type)` 四元组去重，删除 **359,402** 条完全重复记录（0.97%）。

**说明**：保留同一用户在同一秒内对不同商品的多条行为（属正常并发操作）；仅删除四个字段完全一致的记录。

### 2.6 数据一致性校验

| 校验项 | 结果 |
|---|---|
| `comment` 勾稽：`good + bad ≤ comments` | 违规 **0** 条 ✅ |
| `action_time` 解析失败 | **0** 条 ✅ |
| 4 张维度表主键重复 | **0** 条 ✅ |

---

## 三、关联完整性（清洗后复核）

| 关联 | 未匹配率 | 说明 |
|---|---:|---|
| `action.user_id → user` | **34.72%** | 与体检一致，`user` 表是活跃用户的子集 |
| `action.sku_id → product` | **0.96%** | 优于体检时的 6.85%（体检按唯一值口径，此处按记录数口径） |
| `product.shop_id → shop` | 0% ✅ | 完全匹配 |

> **口径差异说明**：体检报告中的 6.85% 是"唯一 sku_id 维度"的未匹配率；本处 0.96% 是"行为记录维度"的未匹配率。两者都对，但用途不同——做商品维度分析用前者，做行为量统计用后者。报告中引用时须标明口径。

---

## 四、产出文件

| 文件 | 内容 |
|---|---|
| `data/processed/action_clean.parquet` | 行为表（36,854,867 行，14 列） |
| `data/processed/user_clean.parquet` | 用户表（1,048,575 行，16 列） |
| `data/processed/product_clean.parquet` | 商品表（352,539 行，9 列） |
| `data/processed/shop_clean.parquet` | 店铺表（10,399 行，11 列） |
| `data/processed/comment_clean.parquet` | 评论表（1,774,233 行，10 列） |
| `outputs/tables/cleaning_log.csv` | 清洗动作逐条记录 |
| `outputs/tables/cleaning_stats.json` | 清洗前后行数与关键指标 |

**格式选择**：用 parquet（snappy 压缩）而非 CSV —— 行为表从 1.53 GB CSV 压到 **754 MB**，且保留列类型，下游无需重复解析。

---

## 五、遗留事项

| # | 事项 | 影响 | 优先级 |
|---|---|---|---|
| 1 | 34.72% 行为用户无画像 | 跨表画像分析样本收缩 | P1 |
| 2 | `age` 编码区间未核实 | 画像结论需标注 | P1 |
| 3 | `province`/`cate`/`brand` 编码未映射 | 只能用编码号，无中文名 | P2 |
| 4 | `module_id` 含义未知 | 渠道漏斗不可做 | P2 |
| 5 | 无金额字段 | GMV/客单价不可算 | — 既定约束 |

---

**结论**：数据已完成标准化，**可用于后续指标聚合与漏斗分析**。

