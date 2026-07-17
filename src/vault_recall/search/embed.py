"""임베딩 provider — 선택적 확장점 (topic-shelf의 provider 패턴 계승).

기본은 None(결정적 코어만). sentence-transformers(BGE-M3 등)가 설치돼 있고
--embed 플래그를 준 경우에만 활성화. 참고: FlagOpen/FlagEmbedding.
"""
from __future__ import annotations


def get_provider(enabled: bool = False):
    if not enabled:
        return None
    try:
        from sentence_transformers import SentenceTransformer  # noqa
    except ImportError:
        return None

    class STProvider:
        """의미 검색 provider. 코어와 같은 인터페이스: query(q, k) → [(name, score, why)]."""

        def __init__(self, model_name: str = "BAAI/bge-m3"):
            self.model = SentenceTransformer(model_name)
            self.names, self.vecs = [], None

        def fit(self, corpus: dict[str, str]):
            self.names = list(corpus)
            self.vecs = self.model.encode([corpus[n] for n in self.names],
                                          normalize_embeddings=True)
            return self

        def query(self, q: str, k: int = 10):
            qv = self.model.encode([q], normalize_embeddings=True)[0]
            sims = self.vecs @ qv
            order = sims.argsort()[::-1][:k]
            return [(self.names[i], float(sims[i]), ["의미 유사"]) for i in order]

    return STProvider()
