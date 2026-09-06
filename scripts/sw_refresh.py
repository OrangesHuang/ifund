#!/usr/bin/env python3
"""申万三级成分采集(legulegu)自适应续采 + 自动合并到服务器。

背景: legulegu 对高频请求有限流(WAF), 连续请求几十次后返回 504/验证页,
冷却一段时间恢复。本脚本把 335 个三级行业分成多个"窗口"渐进采集:
每窗口内 2s 间隔逐个拉; 连续失败达到阈值即结束窗口, 冷却 cooldown 秒后重试;
已采到的三级行业自动跳过(续采)。全部完成后把结果 upsert 合并到生产服务器。

用法(在 Mac, 需能访问 legulegu):
  cd <repo>/backend
  DB_PATH=/tmp/sw_scratch.db IFUND_BACKEND_DIR=$PWD ./venv/bin/python3 ../scripts/sw_refresh.py \
      --db /tmp/sw_scratch.db --cooldown 2400 --max-windows 60 --auto-push

--db 为本地目标 sqlite(由 schema_sqlite.sql 初始化 + 一条 fetch_tasks 占位行)。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# ---- 窗口内参数(与 sw_worker 原逻辑一致/略保守) ----
SLEEP = 2.0          # 行业间隔
COOLDOWN = 1800      # 触发限流后的冷却秒数(默认 30 分钟)
MAX_CONSEC_FAIL = 2  # 连续失败次数达到即结束当前窗口
MAX_WINDOWS = 60
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def covered_l3(db_path: str) -> set[str]:
    c = sqlite3.connect(db_path)
    try:
        return {r[0] for r in c.execute(
            "SELECT sw_l3 FROM stock_industry WHERE sw_l3 != '' GROUP BY sw_l3")}
    finally:
        c.close()


def merge_to_server(db_path: str, host: str = "47.93.237.127") -> None:
    """把本地表中 legulegu 行 upsert 到服务器(保留服务器 manual/em_industry)。"""
    c = sqlite3.connect(db_path)
    rows = [dict(zip([d[0] for d in c.execute("PRAGMA table_info(stock_industry)")], r))
            for r in c.execute("SELECT * FROM stock_industry WHERE source='legulegu'")]
    c.close()
    payload = json.dumps(rows, ensure_ascii=False)
    script = r'''
import json, sqlite3, sys
rows = json.load(sys.stdin)
c = sqlite3.connect("/root/ifund/backend/data.db")
n_up, n_new, n_skip = 0, 0, 0
for r in rows:
    old = c.execute("SELECT id, manual, em_industry FROM stock_industry WHERE stock_code=?", (r["stock_code"],)).fetchone()
    if old and old[1]:
        n_skip += 1; continue
    vals = dict(r)
    if old:
        c.execute("UPDATE stock_industry SET stock_name=?,market=?,sw_l1=?,sw_l2=?,sw_l3=?,em_industry=?,source=?,manual=?,updated_at=datetime('now') WHERE stock_code=?", tuple(vals.get(k,"") for k in ("stock_name","market","sw_l1","sw_l2","sw_l3")) + (vals.get("em_industry",""), vals.get("source",""), old[1], r["stock_code"]))
        n_up += 1
    else:
        c.execute("INSERT INTO stock_industry (stock_code,stock_name,market,sw_l1,sw_l2,sw_l3,em_industry,source,manual,updated_at) VALUES (?,?,?,?,?,?,?,?,0,datetime('now'))", tuple(r.get(k,"") for k in ("stock_code","stock_name","market","sw_l1","sw_l2","sw_l3","em_industry","source")))
        n_new += 1
c.commit()
print(f"merge: new={n_new} updated={n_up} manual_skipped={n_skip}")
'''
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", f"root@{host}", "python3 -c " + json.dumps(script)],
        input=payload, capture_output=True, text=True, timeout=300,
    )
    log(f"merge rc={proc.returncode}: {(proc.stdout or proc.stderr).strip()[-200:]}")


def fetch_industry(code: str):
    import requests
    import pandas as pd
    from io import StringIO
    url = f"https://legulegu.com/stockdata/index-composition?industryCode={code}"
    try:
        resp = requests.get(url, headers=UA, timeout=25)
        return pd.read_html(StringIO(resp.text))[0]
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cooldown", type=int, default=COOLDOWN)
    ap.add_argument("--max-windows", type=int, default=MAX_WINDOWS)
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    # 目录依赖 import(akshare) 放这里: Mac 上可用即可
    import akshare as ak
    from app.stock_industry.crud import industry_crud  # noqa: F401  (确保依赖表结构)

    db_path = Path(args.db)
    for window in range(1, args.max_windows + 1):
        log(f"窗口 {window}/{args.max_windows} 开始, 已覆盖 {len(covered_l3(db_path))} 个三级行业")
        try:
            third = ak.sw_index_third_info()
        except Exception as exc:
            log(f"获取三级目录失败(限流?): {exc}")
            time.sleep(args.cooldown)
            continue
        if third is None:
            time.sleep(args.cooldown)
            continue
        targets = [(str(r["行业代码"]), r["行业名称"], r["上级行业"]) for _, r in third.iterrows()]
        covered = covered_l3(db_path)
        pending = [t for t in targets if t[1] not in covered]
        if not pending:
            log("全部行业已覆盖 ✔")
            if not args.no_push:
                merge_to_server(str(db_path))
            return 0
        log(f"剩余 {len(pending)} 个行业待采")
        # 复用原 worker 的完整链回溯(l1/l2), 与页面「采集」行为一致
        from app.stock_industry.fetch import sw_worker as m
        l2_to_l1 = m._l2_to_l1()
        db = sqlite3.connect(db_path)
        consec_fail = 0
        done_in_window = 0
        for icode, l3name, l2name in pending:
            frame = m._fetch_cons(icode)
            if frame is None:
                consec_fail += 1
                log(f"  ✗ {l3name} ({icode}) 连续失败 {consec_fail}")
                if consec_fail >= MAX_CONSEC_FAIL:
                    log("达到窗口失败阈值, 进入冷却")
                    break
                time.sleep(1.5)
                continue
            consec_fail = 0
            rows = 0
            for raw_code, raw_name in zip(frame["股票代码"], frame["股票简称"]):
                code = str(raw_code).split(".", maxsplit=1)[0].strip()
                if not code:
                    continue
                db.execute("INSERT OR REPLACE INTO stock_industry "
                           "(stock_code,stock_name,market,sw_l1,sw_l2,sw_l3,source,updated_at) VALUES (?,?,?,?,?,?, 'legulegu', datetime('now'))",
                           (code, str(raw_name).strip(), "A",
                            l2_to_l1.get(l2name, ""), l2name, l3name))
                rows += 1
            db.commit()
            done_in_window += 1
            log(f"  ✔ {l3name} ({icode}) +{rows} 行 (窗口内完成 {done_in_window})")
            time.sleep(SLEEP)
        db.close()
        left = len(pending) - done_in_window
        if left > 0:
            log(f"窗口结束, 仍剩约 {left} 行业, 冷却 {args.cooldown}s")
            time.sleep(args.cooldown)
        elif covered.union({t[1] for t in pending}) and done_in_window == len(pending):
            log("本窗口清空剩余 ✔")
    log("达到最大窗口数, 未完成。")
    return 2


if __name__ == "__main__":
    sys.exit(main())
