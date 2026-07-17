"""하이브리드 소환 검색 = BM25 + 그래프 부스트 (+ 선택적 임베딩 RRF 융합).

그래프 부스트: 검색 상위 노트의 위키링크 이웃을 근거 후보로 확장(감쇠 점수).
'연결된 노트는 함께 소환된다' — 위키링크를 실제 검색 신호로 쓰는 것이 핵심 차별.
"""
from __future__ import annotations

from .bm25 import BM25

GRAPH_DAMP = 0.30    # 이웃으로 전파되는 점수 비율 (절제 실험: 랭킹 효과 0 — 근거 확장용)
MOC_PENALTY = 0.5    # 허브(MOC)가 개별 근거를 밀어내지 않도록 (절제 실험: MRR +0.017)
RRF_K = 60


def rrf(rankings: list[list[str]]) -> dict[str, float]:
    fused = {}
    for ranking in rankings:
        for rank, name in enumerate(ranking):
            fused[name] = fused.get(name, 0.0) + 1.0 / (RRF_K + rank + 1)
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

    # 선택적 임베딩: RRF 융합
    if embed_provider is not None:
        emb = embed_provider.query(query, k=k * 3)
        bm_rank = [n for n, _, _ in seeds]
        em_rank = [n for n, _, _ in emb]
        fused = rrf([bm_rank, em_rank])
        for n in fused:
            why.setdefault(n, []).append("의미 검색 융합")
        scores = {n: fused.get(n, 0.0) + 0.001 * scores.get(n, 0.0)
                  for n in set(fused) | set(scores)}

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
