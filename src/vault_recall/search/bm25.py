"""BM25 검색 — 표준 라이브러리만, 한국어 대응 토크나이저(음절 bigram).

knowledge-ops의 키워드-교집합 데모를 진짜 랭킹 검색으로 대체.
결정적: 같은 코퍼스·같은 질의 = 같은 순위.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_ASCII = re.compile(r"[a-z0-9_+#\.]{2,}")
_HANGUL = re.compile(r"[가-힣]{2,}")


def tokenize(text: str) -> list[str]:
    """영문 소문자 단어 + 한글 음절 bigram (+ 전체 어절)."""
    text = text.lower()
    toks = _ASCII.findall(text)
    for word in _HANGUL.findall(text):
        toks.append(word)
        toks.extend(word[i:i + 2] for i in range(len(word) - 1))
    return toks


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75, tokenizer=None):
        self.k1, self.b = k1, b
        self.tokenize = tokenizer or tokenize
        self.docs: dict[str, Counter] = {}
        self.df: Counter = Counter()
        self.avgdl = 1.0

    def fit(self, corpus: dict[str, str]) -> "BM25":
        for name, text in corpus.items():
            tf = Counter(self.tokenize(text))
            self.docs[name] = tf
            for t in tf:
                self.df[t] += 1
        n_docs = max(len(self.docs), 1)
        self.avgdl = sum(sum(tf.values()) for tf in self.docs.values()) / n_docs or 1.0
        self.n_docs = n_docs
        return self

    def ideal_score(self, q: str) -> float:
        """질의의 이상 점수(모든 토큰 tf=1 매칭 가정 상한 근사) — 공백 판정의 분모."""
        return sum(self.idf(t) for t in set(self.tokenize(q))) or 1e-9

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    def query(self, q: str, k: int = 10) -> list[tuple[str, float, list[str]]]:
        """→ [(문서명, 점수, 매칭 근거 토큰)] 점수 내림차순."""
        q_toks = set(self.tokenize(q))
        scored = []
        for name, tf in self.docs.items():
            dl = sum(tf.values())
            score, matched = 0.0, []
            for t in q_toks:
                if t not in tf:
                    continue
                num = tf[t] * (self.k1 + 1)
                den = tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                score += self.idf(t) * num / den
                matched.append(t)
            if score > 0:
                scored.append((name, score, sorted(matched, key=len, reverse=True)[:6]))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]
