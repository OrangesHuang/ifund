"""份额类别去重：同一只基金的 A/C/E/D 等份额持仓 100% 相同、净值仅因费率微差，
若同时进入分析池会被当成多只独立基金，虚高分散度、污染聚类与穿透。

识别规则（两层，宁可漏合并不可错合并）：
1. 名称去掉末尾份额字母（及「(前端)/(后端)」）后相同 → 同一基金的候选份额组；
2. 组内再按前十大股票持仓重叠度确认（重叠 ≥ 阈值才真正合并），避免「去字母后偶然同名」
   的两只不同基金被错并。

保留规则：组内按 (sharpe_3y 降序, code 升序) 取第一只，其余剔除。份额间业绩几乎相同，
保留谁影响极小，确定性规则保证可复现。
"""
from __future__ import annotations

import re

_SIDE = re.compile(r"[（(](前|后)端[）)]\s*$")    # 「(后端)/(前端)」等申购方式后缀
_TAIL = re.compile(r"[A-Za-z]+$")                 # 末尾连续英文字母（份额代码）
_OVERLAP_MIN = 0.7                                # 持仓重叠度阈值（交集 / 较小集）


def _base_name(name: str) -> str:
    """去掉份额后缀，得到「基金主体名」用于分组。"""
    s = _SIDE.sub("", (name or "").strip())
    s = _TAIL.sub("", s).strip()
    return s


def _stock_set(item: dict) -> frozenset[str]:
    """一只基金前十大股票代码集合（用于持仓一致性确认）。"""
    return frozenset(
        (h.get("asset_code") or "").strip()
        for h in (item.get("holdings") or [])
        if h.get("holding_type") == "stock" and (h.get("asset_code") or "").strip()
    )


def _keep_first(group: list[dict]) -> dict:
    """组内按 (sharpe_3y 降序, code 升序) 取保留的那只。"""
    return sorted(
        group,
        key=lambda x: (-(x.get("sharpe_3y") if x.get("sharpe_3y") is not None else -1e9),
                       str(x.get("code") or "")),
    )[0]


def dedup_share_classes(items: list[dict]) -> tuple[list[dict], list[str]]:
    """合并同一只基金的多份额。返回 ``(去重后 items, 被剔除的 code 列表)``。"""
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(_base_name(it.get("name", "")), []).append(it)

    kept: list[dict] = []
    removed: list[str] = []
    for grp in groups.values():
        if len(grp) == 1:
            kept.append(grp[0])
            continue
        # 同 base_name 组内，按持仓重叠度聚成「真份额子组」，每个子组只留一只
        used = [False] * len(grp)
        sets = [_stock_set(it) for it in grp]
        for i in range(len(grp)):
            if used[i]:
                continue
            sub = [grp[i]]
            used[i] = True
            for j in range(i + 1, len(grp)):
                if used[j]:
                    continue
                si, sj = sets[i], sets[j]
                # 持仓为空（无股票，如纯债）时仅凭同名即合并；否则要求重叠达阈值
                inter = len(si & sj)
                small = min(len(si), len(sj))
                same = (inter / small >= _OVERLAP_MIN) if small else (si == sj)
                if same:
                    sub.append(grp[j])
                    used[j] = True
            keep = _keep_first(sub)
            kept.append(keep)
            removed.extend(it.get("code") for it in sub if it is not keep and it.get("code"))
    return kept, removed
