"""聚类编排：快照 items + 指标 → 簇列表 + 元信息。"""
from __future__ import annotations

import numpy as np  # pylint: disable=import-error

from app.cluster.algo import clustering, dedup, labeling, matrix, scoring, similarity

MIN_FUNDS = 3
CLUSTER_FLOOR = 8
CLUSTER_CEIL = 40


def _target_clusters(n: int) -> int:
    return int(np.clip(n // 10, CLUSTER_FLOOR, CLUSTER_CEIL))


def run(items: list[dict], metrics: dict[str, dict]) -> dict | None:
    """返回 ``{"clusters": [...], "meta": {...}}``；可聚类基金 <3 返回 None。

    无股票持仓的基金不丢弃，单独归「其他」簇（cluster_id=0）追加在末尾。
    综合分在「可聚类 + 其他」全量池上计算，保证 z 标准一致。

    入口先做份额去重（A/C/E/D 等同一只基金只保留一个份额），避免同基金多份额污染聚类。
    """
    items, share_removed = dedup.dedup_share_classes(items)
    mat, dropped_codes = matrix.build(items)
    n = len(mat.codes)
    if n < MIN_FUNDS:
        return None

    all_codes = mat.codes + dropped_codes
    scores = scoring.composite_scores(all_codes, metrics)

    target = _target_clusters(n)
    dist = similarity.distance_matrix(mat.stk_matrix, mat.ind_matrix)
    labels = clustering.fcluster_ward(dist, target)
    clusters = labeling.assemble(mat, labels, scores, metrics)
    if dropped_codes:
        clusters.append(labeling.other_cluster(dropped_codes, scores, metrics))
    return {
        "clusters": clusters,
        "meta": {"n": n, "dropped": len(dropped_codes), "total": len(all_codes),
                 "t": len(clusters), "target": target, "share_merged": len(share_removed)},
    }
