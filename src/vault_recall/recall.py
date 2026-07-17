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

# 공백 판정: top점수/이상점수 비율 — 스케일 불변 (절제 실험으로 캘리브레이션:
# in-vault 중앙값 1.23 vs out-vault 중앙값 0.17)
RATIO_GAP = 0.30    # 미만 → 공백 선언
RATIO_WEAK = 0.60   # 미만 → 약한 근거 경고


@dataclass
class RecallResult:
    query: str
    hits: list           # [(Note, score, why)]
    gap: bool            # 강한 공백 (근거 부족 선언)
    uncovered: list      # 볼트가 커버 못한 질의 어절
    verified_only: bool = False
    confidence: str = "충분"   # 충분 | 약함 | 공백
    ratio: float = 0.0         # top점수 / 이상점수

    def to_markdown(self) -> str:
        lines = [f"# 소환: {self.query}", ""]
        if self.confidence == "공백":
            lines += ["> ⚠ **근거 부족(공백)** — 이 질의에 대한 지식이 볼트에 없다.",
                      "> 지어내지 않는다. 아래는 가장 가까운 카드일 뿐이다.", ""]
        elif self.confidence == "약함":
            lines += ["> ⚠ **근거 약함** — 인접 주제 카드만 있다. 결론에 쓰기 전 검증할 것.", ""]
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
            verified_only: bool = False, embed_provider=None, reranker=None) -> RecallResult:
    type_of = {n.name: n.type for n in notes.values()}
    texts = {n.name: n.search_text() for n in notes.values()} if reranker else None
    ranked = hybrid.search(bm25, graph, query, k=k * 2, embed_provider=embed_provider,
                           type_of=type_of, reranker=reranker, texts=texts)
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
    ratio = top / bm25.ideal_score(query)
    confidence = "공백" if ratio < RATIO_GAP else ("약함" if ratio < RATIO_WEAK else "충분")
    gap = confidence == "공백"

    # 정직한 공백: 질의 어절 중 어떤 상위 근거에도 등장하지 않는 것
    covered_tokens = set()
    for note, _, _ in hits:
        covered_tokens |= set(tokenize(note.search_text()))
    uncovered = [w for w in _query_words(query)
                 if not (set(tokenize(w)) & covered_tokens)]
    return RecallResult(query=query, hits=hits, gap=gap,
                        uncovered=uncovered, verified_only=verified_only,
                        confidence=confidence, ratio=ratio)
