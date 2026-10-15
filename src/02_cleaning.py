from pathlib import Path
import json 
import csv
import numpy as np
import pandas as pd
import sys
import warnings
import argparse
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_codes as CFG  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'
PROCESSED = ROOT / 'data' / 'processed'
OUT = ROOT / 'outputs' / 'tables'
PROCESSED.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

CHUNK = 1_000_000

_logs = []
_stats = {}
def log(msg):
    print(msg, flush=True)

def record(table: str, step: str, before, after, detail: str = "") -> None:
    """记录一条清洗动作。"""
    _logs.append(
        {
            "table": table,
            "step": step,
            "before": before,
            "after": after,
            "delta": (after - before) if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None,
            "detail": detail,
        }
    )


# ==============================================================================
def clean_user():
    log('  [清洗] user')
    df = pd.read_csv(RAW / 'jdata_user.csv')
    n0 = len(df)
    record("user", "读取", n0, n0)

    # sex = -1 -> Nan
    n_ph = int((df['sex'] == -1).sum())
    df.loc[df['sex'] == -1, 'sex'] = np.nan
    record("user", "sex 占位值(-1)转NaN", n0, n0, f"{n_ph} 条")

    # 类型规范
    for c in ["user_id", "user_lv_cd", "age", "sex", "city_level", "province", "city", "county"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["user_id"] = df["user_id"].astype("int64")
    df["user_lv_cd"] = df["user_lv_cd"].astype("int8")

    # 时间规范
    raw_reg = df['user_reg_tm'].astype(str)
    df["user_reg_tm"] = raw_reg
    df['user_reg_dt'] = pd.to_datetime(raw_reg, format= "mixed", errors='coerce')
    unparsable_n = int(df['user_reg_dt'].isna().sum())
    record("user", "注册时间标准化", n0, n0, f"{unparsable_n} 条无法解析")


    # 派生：注册年份
    df["reg_year"] = df["user_reg_dt"].dt.year.astype("Int16")

    # 标签列（可选，便于可读）
    df["sex_label"] = df["sex"].map(CFG.SEX_MAP)
    df["age_label"] = df["age"].map(CFG.AGE_MAP)
    df["lv_label"] = df["user_lv_cd"].map(CFG.USER_LV_MAP)
    df["city_level_label"] = df["city_level"].map(CFG.CITY_LEVEL_MAP)
    df["province_code"] = df["province"].map(CFG.PROVINCE_MAP)

    df["user_reg_tm"] = raw_reg
    _stats["user"] = {"rows_raw": n0, "rows_clean": len(df), "sex_placeholder_fixed": n_ph}
    log(f"  -> {len(df):,} 行，sex 占位修正 {n_ph:,} 条")
    return df

def clean_product() -> pd.DataFrame:
    log("  [清洗] product")
    df = pd.read_csv(RAW / "jdata_product.csv")
    n0 = len(df)
    record("product", "读取", n0, n0)

    df["sku_id"] = df["sku_id"].astype("int64")
    for c in ["brand", "shop_id", "cate"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int32")

    raw_mt = df["market_time"].astype(str)
    df["market_dt"] = pd.to_datetime(raw_mt, format= "mixed", errors="coerce")
    df["market_year"] = df["market_dt"].dt.year.astype("Int16")
    df["market_time"] = raw_mt

    df["cate_code"] = df["cate"].map(lambda x: f"C{int(x):02d}" if pd.notna(x) else None)
    _stats["product"] = {"rows_raw": n0, "rows_clean": len(df)}
    log(f"  -> {len(df):,} 行")
    return df

def clean_shop() -> pd.DataFrame:
    log("  [清洗] shop")
    df = pd.read_csv(RAW / "jdata_shop.csv")
    n0 = len(df)
    record("shop", "读取", n0, n0)

    # 占位值 -> NaN
    n_score_ph = int(df["shop_score"].isin(CFG.SHOP_SCORE_PLACEHOLDER).sum())
    df.loc[df["shop_score"].isin(CFG.SHOP_SCORE_PLACEHOLDER), "shop_score"] = np.nan
    record("shop", "shop_score 占位值(-1,0)转NaN", n0, n0, f"{n_score_ph} 条")

    df["vender_id"] = df["vender_id"].astype("int64")
    df["shop_id"] = df["shop_id"].astype("int64")
    for c in ["fans_num", "vip_num"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("int64")
    df["cate"] = pd.to_numeric(df["cate"], errors="coerce").astype("Int32")

    raw_reg = df["shop_reg_tm"].astype(str)
    df["shop_reg_dt"] = pd.to_datetime(raw_reg, format= "mixed", errors="coerce")
    df["shop_reg_tm"] = raw_reg

    # 派生：粉丝转化会员率（会员/粉丝），粉丝为 0 时为 NaN
    df["vip_per_fans"] = np.where(
        df["fans_num"] > 0, df["vip_num"] / df["fans_num"], np.nan
    ).round(6)

    df["cate_code"] = df["cate"].map(lambda x: f"C{int(x):02d}" if pd.notna(x) else None)
    _stats["shop"] = {
        "rows_raw": n0,
        "rows_clean": len(df),
        "score_placeholder_fixed": n_score_ph,
        "cate_missing": int(df["cate"].isna().sum()),
    }
    log(f"  -> {len(df):,} 行，评分占位修正 {n_score_ph:,} 条")
    return df

def clean_comment() -> pd.DataFrame:
    log("  [清洗] comment")
    df = pd.read_csv(RAW / "jdata_comment.csv")
    n0 = len(df)
    record("comment", "读取", n0, n0)

    raw_dt = df["dt"].astype(str)
    df["dt"] = pd.to_datetime(raw_dt, format= "mixed", errors="coerce")
    df["date_str"] = raw_dt
    df["sku_id"] = df["sku_id"].astype("int64")
    for c in ["comments", "good_comments", "bad_comments"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("int32")

    # 勾稽校验：good + bad <= comments
    viol = int((df["good_comments"] + df["bad_comments"] > df["comments"]).sum())
    record("comment", "勾稽校验 good+bad<=comments", viol, 0, f"违规 {viol} 条")

    # 派生：中评数、好评率、差评率
    df["neutral_comments"] = (df["comments"] - df["good_comments"] - df["bad_comments"]).astype("int32")
    df["good_rate"] = (df["good_comments"] / df["comments"]).round(6)
    df["bad_rate"] = (df["bad_comments"] / df["comments"]).round(6)

    # 派生时间维度
    df["year"] = df["dt"].dt.year.astype("Int16")
    df["month"] = df["dt"].dt.month.astype("Int8")
    df["weekday"] = df["dt"].dt.weekday.astype("Int8")

    _stats["comment"] = {
        "rows_raw": n0,
        "rows_clean": len(df),
        "integrity_violation": viol,
        "total_comments": int(df["comments"].sum()),
    }
    log(f"  -> {len(df):,} 行，勾稽违规 {viol} 条")
    return df


# ================================================================ 行为表清洗（分块）
def clean_action_chunked(user_ids: set, sku_ids: set, sample: bool = False) -> dict:
    """行为表分块清洗并分片写出，最后合并为单一 parquet。"""
    log("  [清洗] action (分块)")
    tmpdir = PROCESSED / "_action_parts"
    tmpdir.mkdir(parents=True, exist_ok=True)

    total_in = total_out = total_dup = 0
    miss_user = miss_sku = unparsable_n = 0
    
    reader = pd.read_csv(RAW / "jdata_action.csv", chunksize=CHUNK, dtype=str, encoding="utf-8")
    parts = []
    for i, chunk in enumerate(reader):
        if sample and (i+1) * CHUNK >= 5_000_000:
            log("  [sample] 已处理 500 万行，停止")
            break

        total_in += len(chunk)

        for col in ["user_id", "sku_id", "module_id"]:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce").astype("int64")
        chunk["type"] = pd.to_numeric(chunk["type"], errors="coerce").astype("int8")

        # 时间标准化：先去 ".0" 后缀，再解析（必须用 format="mixed" 兼容多形态）
        t_raw = chunk["action_time"].str.replace(r"\.0$", "", regex=True)
        t = pd.to_datetime(t_raw, format="mixed", errors="coerce")
        unparsable_n += int(t.isna().sum())

        chunk["action_dt"] = t
        chunk["dt"] = t.dt.normalize()
        chunk["hour"] = t.dt.hour.astype("Int8")
        chunk["weekday"] = t.dt.weekday.astype("Int8")
        chunk["is_weekend"] = t.dt.weekday >= 5
        # 保留规范化后的字符串原值（注意：不可赋值为 datetime，否则丢失原始信息）
        chunk["action_time"] = t_raw

        chunk["user_has_profile"] = chunk["user_id"].isin(user_ids)
        chunk["sku_has_product"] = chunk["sku_id"].isin(sku_ids)
        miss_user += int((~chunk["user_has_profile"]).sum())
        miss_sku += int((~chunk["sku_has_product"]).sum())

        chunk["type_label"] = chunk["type"].map(CFG.ACTION_TYPE)
        chunk["is_funnel"] = chunk["type"].isin(CFG.FUNNEL_ORDER)

        key_cols = ["user_id", "sku_id", "action_time", "type"]
        before = len(chunk)
        chunk = chunk.drop_duplicates(subset=key_cols, keep="first")
        total_dup += before - len(chunk)

        cols = [
            "user_id", "sku_id", "action_time", "module_id", "type", "type_label",
            "is_funnel", "action_dt", "dt", "hour", "weekday", "is_weekend",
            "user_has_profile", "sku_has_product",
        ]
        chunk = chunk[cols]
        total_out += len(chunk)
    
        p = tmpdir / f"part_{i:04d}.parquet"
        chunk.to_parquet(p, engine="pyarrow", index=False, compression="snappy")
        parts.append(p)
        if (i + 1) % 10 == 0:
            log(f"    已处理 {(i+1)*CHUNK:,} 行 ...")

    # 合并分片
    log(f"  合并 {len(parts)} 个分片 -> action_clean.parquet")
    import pyarrow.parquet as pq
    import pyarrow as pa

    writer = None
    for p in parts:
        tb = pq.read_table(p)
        if writer is None:
            writer = pq.ParquetWriter(PROCESSED / "action_clean.parquet", tb.schema, compression="snappy")
        writer.write_table(tb)
    if writer:
        writer.close()

    # 清理临时分片
    # 说明：沙箱环境下 unlink 可能被 safe-delete 拦截，失败不影响结果，仅告警
    for p in parts:
        try:
            p.unlink()
        except OSError as e:
            log(f"  [warn] 临时分片未删除：{p.name}（{type(e).__name__}）")
    try:
        tmpdir.rmdir()
    except OSError as e:
        log(f"  [warn] 临时目录未删除：{tmpdir}（{type(e).__name__}）")

    _stats["action"] = {
        "rows_raw": total_in,
        "rows_clean": total_out,
        "dup_removed": total_dup,
        "unparsable_time": unparsable_n,
        "unmatched_user": miss_user,
        "unmatched_sku": miss_sku,
        "unmatched_user_rate": round(miss_user / total_in, 6) if total_in else None,
        "unmatched_sku_rate": round(miss_sku / total_in, 6) if total_in else None,
    }
    record("action", "读取+清洗+去重", total_in, total_out, f"去重删除 {total_dup} 条")
    log(
        f"  -> {total_out:,} 行（原始 {total_in:,}，去重删除 {total_dup:,}）"
    )
    return _stats["action"]

# ================================================================ 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="行为表仅处理 500 万行")
    args = ap.parse_args()

    if args.sample:
        log("=== SAMPLE 模式：行为表仅处理 500 万行 ===")

    log("=" * 60)
    log("京东数据清洗与标准化")
    log("=" * 60)

    user = clean_user()
    product = clean_product()
    shop = clean_shop()
    comment = clean_comment()

    user_ids = set(user["user_id"].tolist())
    sku_ids = set(product["sku_id"].tolist())

    clean_action_chunked(user_ids, sku_ids, sample=args.sample)

    # 写出维度表
    log("[写出] 维度表 -> data/processed/")
    for name, df in [("user", user), ("product", product), ("shop", shop), ("comment", comment)]:
        df.to_parquet(PROCESSED / f"{name}_clean.parquet", engine="pyarrow", index=False, compression="snappy")
        log(f"  {name}_clean.parquet  ({len(df):,} 行)")

    # 清洗日志
    pd.DataFrame(_logs).to_csv(OUT / "cleaning_log.csv", index=False, encoding="utf-8-sig")

    # 清洗统计
    _stats["confidence"] = CFG.describe_confidence()
    with open(OUT / "cleaning_stats.json", "w", encoding="utf-8") as f:
        json.dump(_stats, f, ensure_ascii=False, indent=2, default=str)

    log("\n===== 清洗完成 =====")
    for t, s in _stats.items():
        if isinstance(s, dict) and "rows_raw" in s:
            log(f"  {t:8s} {s['rows_raw']:>12,} -> {s['rows_clean']:>12,}")
    log(f"\n产出：{PROCESSED}")
    log(f"日志：{OUT / 'cleaning_log.csv'}")

if __name__ == "__main__":
    main()
