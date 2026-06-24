"""iFund CLI 入口：参数解析 + 分发。

运行：``./venv/bin/python3 -m cli <组> <命令>`` 或 backend 根的 ``ifund_cli.py`` 薄壳。
通用选项 --json（紧凑 JSON）/ --user N（默认 1，主用户）通过 parent parser 注入每个命令。
"""
from __future__ import annotations

import argparse

from . import analyze, fetch, holdings, preset, trade


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="紧凑 JSON 输出")
    common.add_argument("--user", type=int, default=1, help="用户 id（默认 1）")

    parser = argparse.ArgumentParser(prog="ifund", description="iFund CLI（直连 data.db）")
    groups = parser.add_subparsers(dest="group", required=True)

    # preset
    g = groups.add_parser("preset", help="预设与镜像快照").add_subparsers(dest="cmd", required=True)
    g.add_parser("list", parents=[common], help="列出预设").set_defaults(fn=preset.cmd_list)
    p = g.add_parser("show", parents=[common], help="查看预设+镜像基金")
    p.add_argument("--id", type=int)
    p.add_argument("--name")
    p.set_defaults(fn=preset.cmd_show)
    p = g.add_parser("snapshot", parents=[common], help="按预设条件重建镜像")
    p.add_argument("--id", type=int)
    p.add_argument("--name")
    p.add_argument("--limit", type=int, default=500)
    p.set_defaults(fn=preset.cmd_snapshot)
    p = g.add_parser("funds", parents=[common], help="基于预设查询基金（镜像内+基础信息，可过滤）")
    p.add_argument("--id", type=int)
    p.add_argument("--name")
    p.add_argument("--code", help="按基金代码精确过滤（逗号多只）")
    p.add_argument("--keyword", help="按名称/代码模糊过滤")
    p.add_argument("--ai", action="store_true", help="附 AI 定性分析列（评级/实力分/运气/集中/结论）")
    p.set_defaults(fn=preset.cmd_funds)
    p = g.add_parser("ai-set", parents=[common],
                     help="写入/更新某基金的 AI 定性分析（OpenClaw 填充，部分字段 upsert）")
    p.add_argument("--code", required=True, help="基金代码")
    p.add_argument("--data", required=True,
                   help="JSON 对象（字面串 / @文件路径 / - 读 stdin）；字段见 schema fund_ai_analysis")
    p.set_defaults(fn=preset.cmd_ai_set)

    # fetch
    g = groups.add_parser("fetch", help="数据拉取").add_subparsers(dest="cmd", required=True)
    g.add_parser("calendar", parents=[common], help="交易日历").set_defaults(fn=fetch.cmd_calendar)
    p = g.add_parser("industry", parents=[common], help="行业映射")
    p.add_argument("--mode", choices=["sw", "em"], default="sw", help="sw=申万三级 / em=东财兜底")
    p.add_argument("--codes", help="仅重采指定三级行业代码(逗号)")
    p.set_defaults(fn=fetch.cmd_industry)
    for name, fn, helptext in [("detail", fetch.cmd_detail, "基金详情"),
                               ("holdings", fetch.cmd_holdings, "基金持仓"),
                               ("nav", fetch.cmd_nav, "基金净值")]:
        p = g.add_parser(name, parents=[common], help=helptext)
        p.add_argument("--codes", help="基金代码(逗号)；省略则按 --types 或全量")
        p.add_argument("--types", help="基金类型(逗号)")
        p.set_defaults(fn=fn)

    # analyze（组合分析）
    g = groups.add_parser("analyze", help="组合分析：预设→仓位建议→穿透/赛道/表现")
    g = g.add_subparsers(dest="cmd", required=True)
    p = g.add_parser("run", parents=[common], help="对预设镜像聚类并算仓位建议")
    p.add_argument("--preset", type=int, required=True, help="预设 id（组合分析必须选一个预设）")
    p.add_argument("--balance", choices=["松", "中", "紧"], help="均衡强度（默认紧 0.14）")
    p.add_argument("--cap", type=float, help="单一行业穿透上限 0.10~0.30（覆盖 balance）")
    p.add_argument("--view", choices=["weights", "industry", "stock", "perf", "all"],
                   default="weights",
                   help="视图：weights=各赛道仓位建议 / industry|stock=底层穿透 / perf=分区间表现 / all")
    p.set_defaults(fn=analyze.cmd_run)

    # holdings（实盘：查询 + 交易 + 调仓建议）
    g = groups.add_parser("holdings", help="实盘：持仓查询/交易/调仓建议")
    g = g.add_subparsers(dest="cmd", required=True)
    g.add_parser("list", parents=[common], help="列出实盘（id/名称/关联预设）").set_defaults(fn=holdings.cmd_list)
    p = g.add_parser("show", parents=[common], help="实际持仓（按赛道簇分组，可加 --penetration 附底层穿透）")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--penetration", action="store_true", help="附带底层穿透（行业/个股）")
    p.add_argument("--by", choices=["industry", "stock", "both"], default="both",
                   help="穿透粒度（仅 --penetration 时生效）")
    p.set_defaults(fn=holdings.cmd_show)
    p = g.add_parser("penetration", parents=[common], help="底层持仓穿透")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--by", choices=["industry", "stock", "both"], default="both")
    p.set_defaults(fn=holdings.cmd_penetration)
    p = g.add_parser("perf", parents=[common], help="组合分区间表现")
    p.add_argument("--pid", type=int, required=True)
    p.set_defaults(fn=holdings.cmd_perf)
    p = g.add_parser("rebalance", parents=[common], help="调仓建议（生成操作指南）")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--preset", type=int, help="临时覆盖关联预设")
    p.add_argument("--cap", type=float, help="单一行业穿透上限 0.10~0.30（默认取实盘 cap）")
    p.add_argument("--band", type=float, help="缓冲带（盘子占比，0~0.10，默认 0.03）")
    p.add_argument("--sell-outside", dest="sell_outside", action="store_true",
                   help="允许卖出赛道外基金去补缺口（默认保留不动）")
    p.add_argument("--trim-overflow", dest="trim_overflow", action=argparse.BooleanOptionalAction,
                   default=True, help="赛道内超配是否可减（默认可减；--no-trim-overflow 则不减只加）")
    p.set_defaults(fn=holdings.cmd_rebalance)

    # 交易写操作（buy/sell/transfer + 交易记录 list/del）
    for name, fn, helptext in [("buy", trade.cmd_buy, "买入一笔"), ("sell", trade.cmd_sell, "卖出一笔")]:
        p = g.add_parser(name, parents=[common], help=helptext)
        p.add_argument("--pid", type=int, required=True)
        p.add_argument("--fund", required=True, help="基金代码(6位数字)或名称")
        p.add_argument("--amount", type=float, required=True, help="金额(元)")
        p.add_argument("--date", help="交易日 YYYY-MM-DD（默认最近交易日）")
        p.set_defaults(fn=fn)
    p = g.add_parser("transfer", parents=[common], help="转仓（卖A买B）")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--from", dest="from_", required=True, help="转出基金 代码/名称")
    p.add_argument("--to", dest="to", required=True, help="转入基金 代码/名称")
    p.add_argument("--amount", type=float, required=True, help="金额(元)")
    p.add_argument("--date", help="交易日 YYYY-MM-DD（默认最近交易日）")
    p.set_defaults(fn=trade.cmd_transfer)
    p = g.add_parser("txns", parents=[common], help="交易记录列表")
    p.add_argument("--pid", type=int, required=True)
    p.set_defaults(fn=trade.cmd_txns)
    p = g.add_parser("txn-del", parents=[common], help="删除一条交易记录（转仓连带删配对）")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--id", type=int, required=True, help="交易记录 id")
    p.set_defaults(fn=trade.cmd_txn_del)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
