from pathlib import Path
import json
import pandas as pd
from datetime import datetime
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'
OUT = ROOT / 'outputs' / 'tables'
OUT.mkdir(parents=True, exist_ok=True)

TABLES = {
    "action": RAW / "jdata_action.csv",
    "comment": RAW / 'jdata_comment.csv',
    "product": RAW / 'jdata_product.csv',
    "shop": RAW / 'jdata_shop.csv',
    "user": RAW / 'jdata_user.csv'
}
ACTION_CHUNK = 1_000_000

def log(msg):
    print(msg, flush=True)

def to_py(o):
    """numpy / pandas 标量 -> 原生 Python，便于 json 序列化。"""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)

def missing_stats(df):
    """空值统计（包括纯空白字符串）"""
    cols = [str(c) for c in df.columns]
    res = {}
    blank = 0
    for col in cols:
        s = df[col]
        na = int(s.isna().sum())
        if s.dtype in ('str', 'string'):
            blank = int((s.str.strip() == "").sum())
        res[col] = {'null_n': na, 'blank_n': blank, 'missing_n': na + blank, 'missing_rate': round((na + blank) / len(df), 4) if len(df) else None}
    return res

def value_counts_top(df, col, top=15):
    if col not in df.columns:
        return {}
    vc = df[col].value_counts(dropna=False).head(top)
    return {str(k): int(v) for k, v in vc.items()}

# ========================================================================
# 1. 结构体检
def profile_table(name, path, df):
    log(f' [体检] {name}: {len(df):,} 行 × {df.shape[1]} 列')
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "n_rows": len(df),
        "n_cols": df.shape[1],
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "missing": missing_stats(df)
    }

# 2. 时间跨度
def time_span(df, col):
    if col not in df.columns:
        return {}
    s = pd.to_datetime(df[col], errors='coerce')
    bad = int(s.isna().sum())
    return {
        "column": col,
        "min": str(s.min()),
        "max": str(s.max()),
        "unparsable_n": bad
    }

# 3.分块扫描
def scan_action(path):
    log(f"  [行为表] 分块扫描行数与分布 （{round(path.stat().st_size / 1024 / 1024 / 1024, 2)} G）")
    reader = pd.read_csv(path, chunksize=ACTION_CHUNK, dtype= str, encoding='utf-8')

    n_chunk = 0
    total = 0
    type_cnt = {}
    module_cnt = {}
    user_ids_seen = set()
    sku_ids_seen = set()
    tmin = None
    tmax = None
    unparsable_n = 0
    missing = {
            "user_id": {"null_n": 0, "blank_n": 0},
            "sku_id": {"null_n": 0, "blank_n": 0},
            "type": {"null_n": 0, "blank_n": 0},
            "module_id": {"null_n": 0, "blank_n": 0},
        }
    for chunk in reader:
        n_chunk += 1
        total += len(chunk)
        columns = []
        if n_chunk == 1:
            columns = list(chunk.columns)
        for k, v in chunk['type'].value_counts().items():
            type_cnt[str(k)] = type_cnt.get(str(k), 0) + int(v)
            # print(type_cnt)
        for k, v in chunk['module_id'].value_counts().items():
            module_cnt[str(k)] = module_cnt.get(str(k), 0) + int(v)
        user_ids_seen.update(chunk['user_id'].astype(str).unique().tolist())
        sku_ids_seen.update(chunk['sku_id'].astype(str).unique().tolist())

        t = pd.to_datetime(chunk['action_time'], errors='coerce')
        cm, cx = t.min(), t.max()
        tmin = cm if tmin is None or cm < tmin else tmin
        tmax = cx if tmax is None or cx > tmax else tmax

        unparsable_n += int(t.isna().sum())
        for c in ["user_id", "sku_id", "type", "module_id"]:
            s = chunk[c]
            missing[c]["null_n"] += int(s.isna().sum())
            missing[c]["blank_n"] += int((s.str.strip() == "").sum())
            missing[c]["missing_n"] = missing[c].get("missing", 0) + missing[c].get("null_n", 0) + missing[c].get("blank_n", 0)
                
        if n_chunk % 10 == 0:
            log(f"  已扫描 {total:,} 行")
    
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "columns": columns,
        "n_rows": total,
        "n_cols": len(columns),
        "n_unique_user_id": len(user_ids_seen),
        "n_unique_sku_id": len(sku_ids_seen),
        "time_min": str(tmin),
        "time_max": str(tmax),
        "time_unparsable_n": unparsable_n,
        "missing": missing,
        "type_distribution": dict(sorted(type_cnt.items(), key=lambda x: x[1], reverse=True)),
        "n_unique_module_id": len(module_cnt),
        "module_id_top_15": dict(sorted(module_cnt.items(), key=lambda x: x[1], reverse=True)[:15]),
        "_unique_user_set": user_ids_seen,
        "_unique_sku_set": sku_ids_seen,
    }

# ========================================================
def write_json(name, payload):
    path = OUT / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=to_py), encoding="utf-8")
    return path

def write_csv(name, data, fieldnames):
    import csv
    path = OUT / name
    with path.open('w', encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    return path

# =================================================================
def main():
    report = {'tables': {}, 'notes': []}
    
    # ---- 小表体检 ----
    dfs = {}
    for name in ['user', 'product', 'shop', 'comment']:
        path = TABLES[name]
        log(f'  [读取]{path.name}')
        df = pd.read_csv(path)
        dfs[name] = df
        report['tables'][name] = profile_table(name, path, df)
    
    # ---- 行为表 ----
    report['tables']['action'] = scan_action(TABLES['action'])

    # ---- 主键唯一性 ---- 
    pk_map = {
        "user": "user_id",
        "product": "sku_id",
        "shop": "shop_id",
        "comment": None
    }
    uniq = {}
    for name, pk in pk_map.items():
        df = dfs[name]
        
        if pk and pk in df.columns:
            uniq[f"{name}.{pk}"] = {
                "n_rows": len(df),
                "n_unique": df[pk].nunique(),
                "dup_rows": len(df) - df[pk].nunique(),
            }
    # 评论表主键（dt, sku_id）
    cdf = dfs['comment']
    key = cdf['dt'].astype(str) + '|' + cdf['sku_id'].astype(str)
    uniq[f'comment.(dt, sku_id)'] = {
        "n_rows": len(cdf),
        "n_unique": key.nunique(),
        "dup_rows": len(cdf) - key.nunique()
    }
    report["primary_key"] = uniq

    # ---- 取值域分布 ----
    vc = {}
    vc["user.user_lv_cd"] = value_counts_top(dfs["user"], "user_lv_cd")
    vc["user.sex"] = value_counts_top(dfs["user"], "sex")
    vc["user.age"] = value_counts_top(dfs["user"], "age", 30)
    vc["user.city_level"] = value_counts_top(dfs["user"], "city_level")
    vc["user.province_top"] = value_counts_top(dfs["user"], "province", 15)
    vc["product.cate"] = value_counts_top(dfs["product"], "cate", 20)
    vc["shop.cate"] = value_counts_top(dfs["shop"], "cate", 20)
    vc["shop.shop_score"] = value_counts_top(dfs["shop"], "shop_score", 20)
    report["value_counts"] = vc

    # ---- 异常值检查 ----
    anom = {}

    # 评论数（小于0，好评论数大于评论数，差评论数大于评论数）
    for col in ['comments', 'good_comments', 'bad_comments']:
        s = pd.to_numeric(cdf[col], errors='coerce')
        anom[f'comment.{col}'] = {
            'min': s.min(),
            'max': s.max(),
            'n_neg': (s < 0).sum(),
            'n_null': s.isna().sum(),
        }
    anom['comment.good_gt_all'] = {'n':int((cdf['good_comments'] > cdf['comments']).sum())}
    anom['comment.bad_gt_all'] = {'n':int((cdf['bad_comments'] > cdf['comments']).sum())}

    # 店铺粉丝/会员
    for col in ["fans_num", "vip_num"]:
        s = pd.to_numeric(dfs["shop"][col], errors="coerce")
        anom[f"shop.{col}"] = {
            "min": str(s.min()),
            "max": str(s.max()),
            "n_neg": int((s < 0).sum()),
            "n_null": int(s.isna().sum()),
        }

    # 商品上架时间
    mt = pd.to_datetime(dfs["product"]["market_time"], errors="coerce")
    anom["product.market_time"] = {
        "min": str(mt.min()),
        "max": str(mt.max()),
        "unparsable_n": int(mt.isna().sum()),
    }

    # 用户注册时间
    rt = pd.to_datetime(dfs["user"]["user_reg_tm"], errors="coerce")
    anom["user.user_reg_tm"] = {
        "min": str(rt.min()),
        "max": str(rt.max()),
        "unparsable_n": int(rt.isna().sum()),
    }
    report["anomaly"] = anom

    # ---- 关联完整性（外键） ----
    action_users = report["tables"]["action"]["_unique_user_set"]
    action_skus = report["tables"]["action"]["_unique_sku_set"]
    user_ids = set(dfs["user"]["user_id"].astype(str))
    sku_ids = set(dfs["product"]["sku_id"].astype(str))
    shop_ids = set(dfs["shop"]["shop_id"].astype(str))
    product_shops = set(dfs["product"]["shop_id"].astype(str))
    comment_skus = set(cdf["sku_id"].astype(str))

    def fk(name, left, right, rname):
        miss = len(left - right)
        return {
            "left": name,
            "right": rname,
            "left_n": len(left),
            "matched_n": len(left & right),
            "unmatched_n": miss, 
            "unmatched_rate": round(miss / len(left), 6)
        }
    
    report["cross_table"] = {
        "action.user_id -> user.user_id": fk(
            "action.user_id", action_users, user_ids, "user.user_id"
        ),
        "action.sku_id -> product.sku_id": fk(
            "action.sku_id", action_skus, sku_ids, "product.sku_id"
        ),
        "product.shop_id -> shop.shop_id": fk(
            "product.shop_id", product_shops, shop_ids, "shop.shop_id"
        ),
        "comment.sku_id -> product.sku_id": fk(
            "comment.sku_id", comment_skus, sku_ids, "product.sku_id"
        ),
    }

    # ---- 时间跨度汇总 ----
    report["time_span"] = {
        "user.user_reg_tm": time_span(dfs["user"], "user_reg_tm"),
        "action.action_time": {
            "min": report["tables"]["action"]["time_min"],
            "max": report["tables"]["action"]["time_max"],
        },
        "comment.dt": time_span(dfs["comment"], "dt"),
        "product.market_time": time_span(dfs["product"], "market_time"),
        "shop.shop_reg_tm": time_span(dfs["shop"], "shop_reg_tm"),
    }

    # ----  用户属性缺失交叉（关键维度） ----
    udf = dfs["user"]
    report["user_missing_pattern"] = {
        "n_all_null_attr": int(
            (
                udf[["age", "sex", "user_lv_cd", "city_level", "province"]]
                .isna()
                .all(axis=1)
            ).sum()
        ),
        "n_age_null": int(udf["age"].isna().sum()),
        "n_sex_null": int(udf["sex"].isna().sum()),
        "n_lv_null": int(udf["user_lv_cd"].isna().sum()),
        "n_city_level_null": int(udf["city_level"].isna().sum()),
        "n_province_null": int(udf["province"].isna().sum()),
    }

    # ---- 清理内部临时对象 ----
    report["tables"]["action"].pop("_unique_user_set", None)
    report["tables"]["action"].pop("_unique_sku_set", None)

    # ---- 输出 ----
    
    # report
    path = write_json("health_report.json", report)
    log(f"  [输出] {path}")

    # vc
    pd.DataFrame([
        {'field': f, 'value': k, 'count': v}
        for f, c in vc.items()
        for k, v in c.items()
    ]
    ).to_csv(OUT / "health_value_counts.csv", index=False, encoding="utf-8")

    # missing
    rows = []
    for tname, t in report['tables'].items():
        for col, m in t.get("missing", {}).items():
            rows.append({"tables": tname, "column": col, **m})
    pd.DataFrame(
        rows
    ).to_csv(OUT / "health_missing.csv", index=False, encoding="utf-8")

    # 汇总表
    summary = []
    for tname, t in report["tables"].items():
        n = t.get("n_rows") or t.get("n_rows_exact")
        summary.append(
            {
                "table": tname,
                "file": t["file"],
                "n_rows": n,
                "n_cols": t["n_cols"],
                "size_mb": round(t["size_bytes"] / 1024 / 1024, 1),
            }
        )
    pd.DataFrame(summary).to_csv(
        OUT / "health_summary.csv", index=False, encoding="utf-8-sig"
    )
    log(f"  [输出] {OUT / 'health_summary.csv'}")

    log("\n===== 体检完成 =====")
    for name, info in report["primary_key"].items():
        log(f"  主键 {name}: 重复 {info['dup_rows']:,} 行")
    for name, info in report["cross_table"].items():
        log(f"  关联 {name}: 未匹配 {info['unmatched_n']:,} ({info['unmatched_rate']})")


if __name__ == "__main__":
    main()







