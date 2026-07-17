"""임베딩 provider — 의미 검색 레이어 (auto 기본화, 우아한 폴백).

- 기본 모델: intfloat/multilingual-e5-small (한국어 지원·경량 ~470MB).
  BAAI/bge-m3 등으로 교체 가능(--model 또는 VAULT_RECALL_EMBED_MODEL).
- e5 계열은 'query: '/'passage: ' 프리픽스가 필수 — 모델명으로 자동 처리.
- 임베딩은 볼트 옆 .recall_cache/에 디스크 캐시(코퍼스 다이제스트 키) —
  두 번째 실행부터 인코딩 없이 즉시 로드.
- sentence-transformers 미설치·모델 다운로드 불가 환경에서는 None을 반환하고
  코어(BM25+그래프)만으로 동작한다. 코어는 임베딩 없이도 완결적이다.

효과크기 근거(eval/gold_paraphrase.json): 어휘가 겹치지 않는 패러프레이즈 질의에서
BM25 하이브리드는 R@5 60%에 머문다(정확 어휘 질의는 100%). 이 갭이 임베딩의 몫이다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

DEFAULT_MODEL = os.environ.get("VAULT_RECALL_EMBED_MODEL", "intfloat/multilingual-e5-small")


def needs_e5_prefix(model_name: str) -> bool:
    return "e5" in model_name.lower()


def corpus_digest(model_name: str, corpus: dict[str, str]) -> str:
    h = hashlib.sha256(model_name.encode())
    for name in sorted(corpus):
        h.update(name.encode())
        h.update(str(len(corpus[name])).encode())
    return h.hexdigest()[:16]


class STProvider:
    """sentence-transformers 기반 provider. 인터페이스: fit(corpus) → query(q, k)."""

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: str | Path | None = None):
        from sentence_transformers import SentenceTransformer  # 호출부에서 ImportError 처리
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.names: list[str] = []
        self.vecs = None

    def _doc(self, text: str) -> str:
        return ("passage: " + text) if needs_e5_prefix(self.model_name) else text

    def _query(self, text: str) -> str:
        return ("query: " + text) if needs_e5_prefix(self.model_name) else text

    def fit(self, corpus: dict[str, str]) -> "STProvider":
        import numpy as np
        self.names = sorted(corpus)
        cache = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache = self.cache_dir / f"emb_{corpus_digest(self.model_name, corpus)}.npz"
            if cache.exists():
                try:
                    data = np.load(cache, allow_pickle=False)
                    cached_names = json.loads(str(data["names"]))
                    if cached_names == self.names:
                        self.vecs = data["vecs"]
                        return self
                except Exception:
                    pass  # 구버전/손상 캐시 → 무시하고 재인코딩
        self.vecs = self.model.encode(
            [self._doc(corpus[n][:1500]) for n in self.names],
            normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        if cache:
            np.savez_compressed(cache, vecs=self.vecs,
                                names=np.array(json.dumps(self.names, ensure_ascii=False)))
        return self

    def query(self, q: str, k: int = 10):
        qv = self.model.encode([self._query(q)], normalize_embeddings=True)[0]
        sims = self.vecs @ qv
        order = sims.argsort()[::-1][:k]
        return [(self.names[i], float(sims[i]), ["의미 유사"]) for i in order]


def get_provider(enabled: bool = True, model_name: str = DEFAULT_MODEL,
                 cache_dir=None, quiet: bool = False):
    """auto 기본화: 가능하면 provider, 불가하면 None(코어만) — 실패해도 죽지 않는다."""
    if not enabled:
        return None
    try:
        return STProvider(model_name, cache_dir=cache_dir)
    except Exception as e:  # ImportError·다운로드 차단·OOM 등 전부 폴백
        if not quiet:
            print(f"[embed] 의미 검색 비활성 ({type(e).__name__}) — BM25+그래프 코어로 동작. "
                  f"활성화: pip install 'vault-recall[embed]'")
        return None


DEFAULT_RERANKER = os.environ.get("VAULT_RECALL_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")


class CrossEncoderReranker:
    """리랭커(cross-encoder) — 후보를 질의-문서 쌍으로 재채점 (FlagEmbedding 리랭커 반영).

    인터페이스: rerank(query, candidates=[(name, text)], k) → [(name, score)]
    """

    def __init__(self, model_name: str = DEFAULT_RERANKER):
        from sentence_transformers import CrossEncoder
        self.model_name = model_name
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list, k: int = 5):
        scores = self.model.predict([(query, text[:1500]) for _, text in candidates])
        order = sorted(range(len(candidates)), key=lambda i: -float(scores[i]))[:k]
        return [(candidates[i][0], float(scores[i])) for i in order]


def get_reranker(enabled: bool = False, model_name: str = DEFAULT_RERANKER,
                 quiet: bool = False):
    if not enabled:
        return None
    try:
        return CrossEncoderReranker(model_name)
    except Exception as e:
        if not quiet:
            print(f"[rerank] 리랭커 비활성 ({type(e).__name__}) — 하이브리드 순위 유지.")
        return None
