"""소환(recall) — 질의에 대해 '내 볼트만 근거'로 답 재료를 소환한다.

되새김/khoj/ragflow 철학의 결정적 구현:
- 근거 카드 + 인용(왜 이 카드가 나왔는지)
- 정직한 공백: 볼트가 커버하지 못하는 질의 어절을 그대로 선언 (할루시네이션 원천 차단)
- LLM 무관여: 답을 '생성'하지 않고 근거를 '소환'만 한다. 생성은 상위 레이어 선택.
"""
from __future__ import annotations

from dataclasses import dataclass

from .parser import Note
from .search.bm25 import BM25, tokenize, _HANGUL, _ASCII
from .search import hybrid

GAP_MIN_SCORE = 2.0   # 이 미만이면 '근거 부족' 선언 (BM25 스케일 경험값, 테스트로 고정)


@dataclass
class RecallResult:
    query: str
    hits: list           # [(Note, score, why)]
    gap: bool            # 전체 근거 부족 여부
    uncovered: list      # 볼트가 커버 못한 질의 어절
    verified_only: bool = False

    def to_markdown(self) -> str:
        lines = [f"# 소환: {self.query}", ""]
        if self.gap:
            lines += ["> ⚠ **근거 부족** — 이 질의에 대한 지식이 볼트에 충분하지 않다.",
                      "> 지어내지 않는다. 아래는 가장 가까운 카드일 뿐이다.", ""]
        for i, (note, score, why) in enumerate(self.hits, 1):
            v = "✓검증" if note.verified else "⚠미검증"
            lines.append(f"## {i}. [[{note.name}]] ({v} · {note.folder} · {score:.2f})")
            if note.description:
                lines.append(f"> {note.description}")
            for w in why[:2]:
                lines.append(f"- {w}")
            lines.append("")
        if self.uncovered:
            lines += ["## 정직한 공백",
                      "볼트가 커버하지 못한 질의 어절 — 다음 학습/기록 후보:",
                      "- " + " · ".join(self.uncovered), ""]
        return "\n".join(lines)


def _query_words(q: str) -> list[str]:
    return _ASCII.findall(q.lower()) + _HANGUL.findall(q)


def perform(notes: dict[str, Note], graph, bm25: BM25, query: str, k: int = 5,
            verified_only: bool = False, embed_provider=None) -> RecallResult:
    ranked = hybrid.search(bm25, graph, query, k=k * 2, embed_provider=embed_provider)
    hits = []
    for name, score, why in ranked:
        note = notes.get(name)
        if note is None:
            continue
        if verified_only and not note.verified:
            continue
        hits.append((note, score, why))
        if len(hits) >= k:
            break

    top = hits[0][1] if hits else 0.0
    gap = top < GAP_MIN_SCORE

    # 정직한 공백: 질의 어절 중 어떤 상위 근거에도 등장하지 않는 것
    covered_tokens = set()
    for note, _, _ in hits:
        covered_tokens |= set(tokenize(note.search_text()))
    uncovered = [w for w in _query_words(query)
                 if not (set(tokenize(w)) & covered_tokens)]
    return RecallResult(query=query, hits=hits, gap=gap,
                        uncovered=uncovered, verified_only=verified_only)
