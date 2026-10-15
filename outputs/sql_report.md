# SQL 评估分析查询结果

数据库：`outputs/results.db`　生成脚本：`src/08_sql_queries.py`

> 所有结果由 SQL 直接查询数据库产出，可重复执行。


## Q01　大盘核心指标（严格口径漏斗）

```sql
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
```

| metric                    | value      | kind   |
|:--------------------------|:-----------|:-------|
| total_action_rows         | 37,210,678 | 计数   |
| total_users_active        | 1,608,707  | 计数   |
| total_skus                | 352,539    | 计数   |
| total_shop                | 10,399     | 计数   |
| total_brands              | 11,199     | 计数   |
| n_days                    | 74         | 计数   |
| funnel_view_strict        | 1,328,942  | 计数   |
| funnel_cart_strict        | 1,328,942  | 计数   |
| funnel_order_strict       | 391,673    | 计数   |
| view2cart_rate_strict     | 1          | 比率   |
| cart2order_rate_strict    | 0.294725   | 比率   |
| overall_conv_rate_strict  | 0.294725   | 比率   |
| good_rate                 | 0.978799   | 比率   |
| bad_rate                  | 0.010373   | 比率   |
| user_profile_coverage     | 0.652788   | 比率   |
| sku_product_coverage      | 0.990449   | 比率   |
| repurchase_rate           | 0.417535   | 比率   |
| avg_orders_per_user_order | 2.081672   | 计数   |

**解读**：严格口径下，浏览→加购→下单整体转化率即评估基准线；复购率反映用户黏性。


## Q02　日行为量 峰值/谷值 Top5

```sql
SELECT dt, action_cnt, active_users, order_cnt,
               ROUND(action_dod, 4)  AS dod,
               ROUND(action_wow, 4)  AS wow
        FROM ts_daily_trend
        ORDER BY action_cnt DESC
        LIMIT 5
```

| dt         | action_cnt   | active_users   | order_cnt   | dod     | wow   |
|:-----------|:-------------|:---------------|:------------|:--------|:------|
| 2018-02-04 | 890,689      | 152,688        | 10,407      | 0.1368  |       |
| 2018-02-06 | 861,864      | 150,573        | 12,275      | 0.0787  |       |
| 2018-02-05 | 798,996      | 150,155        | 11,972      | -0.1029 |       |
| 2018-02-01 | 795,056      | 141,054        | 7,774       |         |       |
| 2018-02-03 | 783,496      | 141,231        | 10,014      | 0.098   |       |

**解读**：峰值日通常对应促销脉冲或数据采集高峰，需结合异常检测判定是真实大促还是流量异常。


## Q03　日行为量 谷值 Bottom5

```sql
SELECT dt, action_cnt, active_users, order_cnt,
               ROUND(action_dod, 4) AS dod
        FROM ts_daily_trend
        ORDER BY action_cnt ASC
        LIMIT 5
```

| dt         | action_cnt   | active_users   | order_cnt   | dod     |
|:-----------|:-------------|:---------------|:------------|:--------|
| 2018-03-27 | 52,571       | 39,606         | 13,367      | -0.8964 |
| 2018-03-28 | 65,389       | 45,433         | 13,122      | 0.2438  |
| 2018-02-15 | 218,475      | 59,270         | 3,966       | -0.2903 |
| 2018-02-16 | 252,460      | 62,944         | 3,147       | 0.1556  |
| 2018-02-17 | 300,974      | 70,316         | 3,466       | 0.1922  |

**解读**：谷值多落在春节等假期窗口，说明用户基数受节假日影响显著。


## Q04　高置信异常日明细（≥2 种方法命中）

```sql
SELECT metric, dt, metric_value,
               ROUND(z_score, 3)      AS z_score,
               ROUND(modified_z, 3)   AS modified_z,
               flag_zscore, flag_iqr, flag_mad,
               anomaly_votes, direction
        FROM anomaly_samples
        ORDER BY metric, dt
```

| metric     | dt         | metric_value   | z_score   | modified_z   | flag_zscore   | flag_iqr   | flag_mad   | anomaly_votes   | direction   |
|:-----------|:-----------|:---------------|:----------|:-------------|:--------------|:-----------|:-----------|:----------------|:------------|
| 下单行为数 | 2018-02-01 | 7,774          | -1.286    | -3.583       | ok            | outlier    | outlier    | 2               | 偏低        |
| 下单行为数 | 2018-02-14 | 7,203          | -1.502    | -4.055       | ok            | outlier    | outlier    | 2               | 偏低        |
| 下单行为数 | 2018-02-15 | 3,966          | -2.726    | -6.727       | warn          | outlier    | outlier    | 3               | 偏低        |
| 下单行为数 | 2018-02-16 | 3,147          | -3.036    | -7.403       | crit          | outlier    | outlier    | 3               | 偏低        |
| 下单行为数 | 2018-02-17 | 3,466          | -2.916    | -7.14        | warn          | outlier    | outlier    | 3               | 偏低        |
| 下单行为数 | 2018-02-18 | 3,650          | -2.846    | -6.988       | warn          | outlier    | outlier    | 3               | 偏低        |
| 下单行为数 | 2018-02-19 | 4,848          | -2.393    | -5.999       | warn          | outlier    | outlier    | 3               | 偏低        |
| 下单行为数 | 2018-02-20 | 5,348          | -2.204    | -5.586       | warn          | outlier    | outlier    | 3               | 偏低        |
| 下单行为数 | 2018-02-21 | 6,223          | -1.873    | -4.864       | ok            | outlier    | outlier    | 2               | 偏低        |
| 下单行为数 | 2018-02-22 | 7,624          | -1.343    | -3.707       | ok            | outlier    | outlier    | 2               | 偏低        |
| 活跃用户数 | 2018-02-15 | 59,270         | -2.413    | -4.158       | warn          | outlier    | outlier    | 3               | 偏低        |
| 活跃用户数 | 2018-02-16 | 62,944         | -2.241    | -3.884       | warn          | outlier    | outlier    | 3               | 偏低        |
| 活跃用户数 | 2018-03-27 | 39,606         | -3.333    | -5.625       | crit          | outlier    | outlier    | 3               | 偏低        |
| 活跃用户数 | 2018-03-28 | 45,433         | -3.061    | -5.19        | crit          | outlier    | outlier    | 3               | 偏低        |
| 行为量     | 2018-02-01 | 795,056        | 2.081     | 4.761        | warn          | outlier    | outlier    | 3               | 偏高        |
| 行为量     | 2018-02-03 | 783,496        | 1.999     | 4.569        | ok            | outlier    | outlier    | 2               | 偏高        |
| 行为量     | 2018-02-04 | 890,689        | 2.763     | 6.343        | warn          | outlier    | outlier    | 3               | 偏高        |
| 行为量     | 2018-02-05 | 798,996        | 2.109     | 4.826        | warn          | outlier    | outlier    | 3               | 偏高        |
| 行为量     | 2018-02-06 | 861,864        | 2.557     | 5.866        | warn          | outlier    | outlier    | 3               | 偏高        |
| 行为量     | 2018-02-15 | 218,475        | -2.026    | -4.777       | warn          | outlier    | outlier    | 3               | 偏低        |
| 行为量     | 2018-02-16 | 252,460        | -1.783    | -4.215       | ok            | outlier    | outlier    | 2               | 偏低        |
| 行为量     | 2018-03-27 | 52,571         | -3.207    | -7.522       | crit          | outlier    | outlier    | 3               | 偏低        |
| 行为量     | 2018-03-28 | 65,389         | -3.116    | -7.31        | crit          | outlier    | outlier    | 3               | 偏低        |

**解读**：多方法一致的异常更可信；偏低型异常集中在特定节假日窗口，偏高型多为采集或大促脉冲。


## Q05　用户等级：规模与下单率

```sql
SELECT
            user_level,
            uv_view  AS view_users,
            uv_order AS order_users,
            ROUND(order_rate * 100, 2) AS order_rate_pct,
            ROUND(user_share * 100, 2) AS share_pct
        FROM agg_user_funnel_by_level
        ORDER BY view_users DESC
```

| user_level   | view_users   | order_users   | order_rate_pct   | share_pct   |
|:-------------|:-------------|:--------------|:-----------------|:------------|
| L1           | 257,696      | 72,263        | 28.04            | 29.71       |
| L6           | 208,562      | 49,052        | 23.52            | 24.05       |
| L5           | 205,165      | 63,777        | 31.09            | 23.66       |
| L7           | 193,989      | 71,331        | 36.77            | 22.37       |
| L4           | 1,790        | 64            | 3.58             | 0.21        |
| L3           | 32           | 8             | 25               | 0           |
| L2           | 8            | 1             | 12.5             | 0           |

**解读**：等级越高（数字越大）通常下单率越高；低等级长尾用户规模大但转化弱，是精细化运营重点。


## Q06　品类 TOP10 行为量与口碑

```sql
SELECT cate_code, sku_cnt, action_cnt, order_users,
               ROUND(action_share * 100, 3) AS action_share_pct,
               ROUND(good_rate * 100, 2)    AS good_rate_pct,
               ROUND(bad_rate * 100, 2)     AS bad_rate_pct
        FROM agg_cate
        ORDER BY action_cnt DESC
        LIMIT 10
```

| cate_code   | sku_cnt   | action_cnt   | order_users   | action_share_pct   | good_rate_pct   | bad_rate_pct   |
|:------------|:----------|:-------------|:--------------|:-------------------|:----------------|:---------------|
| C07         | 72,420    | 11,628,078   | 149,486       | 31.551             | 97.94           | 1.1            |
| C34         | 7,509     | 2,012,745    | 31,176        | 5.461              | 97.52           | 1.23           |
| C27         | 9,720     | 1,831,285    | 39,574        | 4.969              | 97.59           | 1.15           |
| C81         | 23,273    | 1,639,136    | 38,760        | 4.447              | 97.32           | 1.24           |
| C75         | 15,876    | 1,296,659    | 48,240        | 3.518              | 97.71           | 1.01           |
| C69         | 12,153    | 1,154,447    | 27,473        | 3.132              | 96.68           | 1.52           |
| C70         | 11,703    | 854,684      | 26,480        | 2.319              | 97.46           | 1.11           |
| C24         | 24,517    | 830,544      | 35,153        | 2.253              | 97.95           | 1              |
| C12         | 5,621     | 813,293      | 13,683        | 2.207              | 97.11           | 1.42           |
| C20         | 4,563     | 782,485      | 14,364        | 2.123              | 97.95           | 1.02           |

**解读**：头部品类贡献主要流量；需关注是否存在高流量高差评的品类，作为质量改进优先级。


## Q07　时段节律：小时行为量排行

```sql
SELECT hour, action_cnt, active_users AS uv,
               ROUND(action_share * 100, 3) AS action_share_pct
        FROM agg_time_hourly
        ORDER BY action_cnt DESC
        LIMIT 8
```

| hour   | action_cnt   | uv      | action_share_pct   |
|:-------|:-------------|:--------|:-------------------|
| 22     | 2,765,956    | 449,845 | 7.433              |
| 21     | 2,679,604    | 472,675 | 7.201              |
| 20     | 2,342,848    | 454,055 | 6.296              |
| 10     | 2,181,669    | 460,411 | 5.863              |
| 23     | 2,048,454    | 334,531 | 5.505              |
| 11     | 2,016,762    | 450,213 | 5.42               |
| 16     | 1,996,588    | 431,792 | 5.366              |
| 15     | 1,970,316    | 428,225 | 5.295              |

**解读**：高峰时段是投放与推送的最佳窗口；凌晨低谷适合做系统维护。


## Q08　星期节律与周末效应

```sql
SELECT weekday, weekday_name, action_cnt, active_users,
               ROUND(action_share * 100, 3) AS action_share_pct
        FROM agg_time_weekday
        ORDER BY weekday
```

| weekday   | weekday_name   | action_cnt   | active_users   | action_share_pct   |
|:----------|:---------------|:-------------|:---------------|:-------------------|
| 0         | 周一           | 5,172,852    | 699,806        | 13.902             |
| 1         | 周二           | 4,816,264    | 679,469        | 12.943             |
| 2         | 周三           | 4,591,981    | 667,310        | 12.341             |
| 3         | 周四           | 5,721,118    | 732,713        | 15.375             |
| 4         | 周五           | 5,496,536    | 722,645        | 14.771             |
| 5         | 周六           | 5,655,563    | 721,967        | 15.199             |
| 6         | 周日           | 5,756,364    | 729,048        | 15.47              |

**解读**：若各星期占比接近，说明不存在显著周末效应，与统计检验结论相互印证。


## Q09　店铺 TOP10（规模与口碑）

```sql
SELECT shop_id, sku_cnt, action_cnt, order_users,
               fans_num, vip_num,
               ROUND(vip_per_fans * 100, 2) AS vip_conv_pct,
               ROUND(shop_score, 2)         AS shop_score
        FROM agg_shop_top100
        ORDER BY action_cnt DESC
        LIMIT 10
```

| shop_id   | sku_cnt   | action_cnt   | order_users   | fans_num   | vip_num   | vip_conv_pct   | shop_score   |
|:----------|:----------|:-------------|:--------------|:-----------|:----------|:---------------|:-------------|
| 8,952     | 313       | 1,059,257    | 4,682         | 0          | 0         |                |              |
| 4,178     | 483       | 996,668      | 14,031        | 0          | 0         |                |              |
| 5,523     | 316       | 667,759      | 8,115         | 0          | 0         |                |              |
| 5,765     | 389       | 640,464      | 7,445         | 0          | 0         |                |              |
| 1,107     | 271       | 566,315      | 4,012         | 0          | 0         |                |              |
| 7,082     | 169       | 538,836      | 5,558         | 0          | 0         |                |              |
| 802       | 286       | 495,245      | 5,217         | 0          | 0         |                |              |
| 3,217     | 253       | 422,464      | 4,556         | 0          | 0         |                |              |
| 8,411     | 175       | 278,413      | 4,916         | 0          | 0         |                |              |
| 5,330     | 2,670     | 256,743      | 8,330         | 0          | 0         |                |              |

**解读**：粉丝转会员率高的店铺私域运营更强；评分为空（原值 -1/0）的店铺不参与评分横向比较。


## Q10　统计检验结论汇总

```sql
SELECT test_name, group_a, group_b, conclusion,
               effect_strength,
               CASE WHEN p_welch  IS NOT NULL THEN ROUND(p_welch, 10) END AS p_welch,
               CASE WHEN p_chi2   IS NOT NULL THEN ROUND(p_chi2, 10)  END AS p_chi2,
               CASE WHEN cohen_d   IS NOT NULL THEN cohen_d END AS cohen_d,
               CASE WHEN cramers_v IS NOT NULL THEN cramers_v END AS cramers_v
        FROM stat_tests
        ORDER BY test_name
```

| test_name                   | group_a             | group_b   | conclusion                                                       | effect_strength   | p_welch   | p_chi2   | cohen_d   | cramers_v   |
|:----------------------------|:--------------------|:----------|:-----------------------------------------------------------------|:------------------|:----------|:---------|:----------|:------------|
| T1 周末效应（日行为量）     | 周末                | 工作日    | 不拒绝H0（无显著差异）                                           | 可忽略            | 0.5057    |          | 0.1592    |             |
| T1b 周末效应（日活跃用户）  | 周末                | 工作日    | 不拒绝H0（无显著差异）                                           | 可忽略            | 0.7457    |          | 0.0755    |             |
| T2 春节假期效应（日行为量） | 春节假期(2/15-2/21) | 常态期    | 拒绝H0（存在显著差异）                                           | 大                | 0.000067  |          | -1.5332   |             |
| T3 用户等级 × 是否下单      | user_lv_cd          | —         | 拒绝H0（存在显著差异）（注意：存在期望频数<5，卡方近似可能不稳） | 弱                |           | 0        |           | 0.1052      |
| T4 性别 × 是否下单          | sex                 | —         | 拒绝H0（存在显著差异）                                           | 可忽略            |           | 0        |           | 0.0626      |
| T5 城市等级 × 是否下单      | city_level          | —         | 拒绝H0（存在显著差异）                                           | 可忽略            |           | 0        |           | 0.0632      |
| T6 年龄段 × 是否下单        | age                 | —         | 拒绝H0（存在显著差异）                                           | 可忽略            |           | 0        |           | 0.0703      |

**解读**：显著性只说明差异存在，效应量说明差异是否值得行动；两者需一起读。
