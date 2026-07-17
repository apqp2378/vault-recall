"""하이브리드 소환 검색 = BM25 + 그래프 부스트 (+ 선택적 임베딩 RRF 융합).

그래프 부스트: 검색 상위 노트의 위키링크 이웃을 근거 후보로 확장(감쇠 점수).
'연결된 노트는 함께 소환된다' — 위키링크를 실제 검색 신호로 쓰는 것이 핵심 차별.
"""
from __future__ import annotations

from .bm25 import BM25

import os

GRAPH_DAMP = 0.30    # 이웃으로 전파되는 점수 비율 (절제 실험: 랭킹 효과 0 — 근거 확장용)
MOC_PENALTY = 0.5    # 허브(MOC)가 개별 근거를 밀어내지 않도록 (절제 실험: MRR +0.017)
RRF_K = 60
# 의미 검색 가중: BM25가 약한(어휘 안 겹치는) 질의에서 정답을 끌어올리려면
# 임베딩 순위에 더 큰 가중이 필요하다. 동일 가중(1.0)이면 어휘 노이즈가 상위를 점령.
EMB_WEIGHT = float(os.environ.get("VAULT_RECALL_EMB_WEIGHT", "2.0"))


def rrf(rankings: list[list[str]], weights: list[float] | None = None) -> dict[str, float]:
    weights = weights or [1.0] * len(rankings)
    fused = {}
    for w, ranking in zip(weights, rankings):
        for rank, name in enumerate(ranking):
            fused[name] = fused.get(name, 0.0) + w / (RRF_K + rank + 1)
    return fused


def search(bm25: BM25, graph, query: str, k: int = 5, embed_provider=None,
           type_of: dict | None = None, reranker=None, texts: dict | None = None):
    """→ [(name, score, why:list[str])]. type_of=MOC 패널티, reranker+texts=재채점."""
    seeds = bm25.query(query, k=k * 3)
    scores = {name: s for name, s, _ in seeds}
    why = {name: [f"직접 매칭: {', '.join(m)}"] for name, _, m in seeds}

    # 그래프 부스트: 상위 시드의 이웃 확장
    for name, s, _ in seeds[:k]:
        for nb in graph.neighbors(name):
            boost = s * GRAPH_DAMP
            if boost > scores.get(nb, 0.0):
                scores[nb] = max(scores.get(nb, 0.0), boost)
                why.setdefault(nb, []).append(f"연결 근거: [[{name}]]의 이웃")

    # 선택적 임베딩: 가중 RRF 융합
    # core(BM25+그래프부스트) 순위와 임베딩 순위를 RRF로 결합.
    # 순수 RRF만 사용 — BM25 원점수를 더하면(구버전 버그) RRF 항을 압도해 임베딩이 묻힌다.
    if embed_provider is not None:
        core_rank = [n for n, _ in sorted(scores.items(), key=lambda x: -x[1])]
        emb = embed_provider.query(query, k=max(len(core_rank), k * 4))
        em_rank = [n for n, _, _ in emb]
        fused = rrf([core_rank, em_rank], weights=[1.0, EMB_WEIGHT])
        emb_top = set(em_rank[:k])
        for n in fused:
            if n in emb_top and n not in set(core_rank[:k]):
                why.setdefault(n, []).append("의미 검색으로 소환")
        scores = fused

    if type_of:
        scores = {n: (s * MOC_PENALTY if type_of.get(n) == "moc" else s)
                  for n, s in scores.items()}
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    if reranker is not None and texts:
        cands = [(n, texts.get(n, "")) for n, _ in ranked[:k * 4]]
        rer = reranker.rerank(query, cands, k=k)
        for n, _ in rer:
            why.setdefault(n, []).append("리랭커 재채점")
        return [(n, s, why.get(n, [])) for n, s in rer]
    return [(n, s, why.get(n, [])) for n, s in ranked[:k]]
