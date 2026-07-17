"""검색 품질 정량 평가 — ragas의 개념을 결정적으로 축소 구현.

골드셋(질의 → 정답 노트)에 대해 Recall@k · MRR을 계산한다.
"내 자료만 근거로 소환된다"는 주장을 숫자로 증빙하는 층.
골드 항목은 부분 문자열로 적어도 되고, 로드 시 실제 노트명으로 해석된다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .search import hybrid
from .search.bm25 import BM25

RATIO_WEAK = 0.60   # recall.RATIO_WEAK와 동일 — '확신 있는 오답'만 실패로 본다


def load_gold(path: str | Path, note_names) -> list[dict]:
    """gold.json: [{"query": "...", "relevant": ["부분문자열", ...]}]"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    resolved = []
    for item in raw:
        rel = []
        for key in item["relevant"]:
            hits = [n for n in note_names if key in n]
            rel.extend(hits if hits else [])
        resolved.append({"query": item["query"], "relevant": sorted(set(rel)),
                         "unresolved": [k for k in item["relevant"]
                                        if not any(k in n for n in note_names)]})
    return resolved


def evaluate(bm25: BM25, graph, gold: list[dict], k: int = 5,
             type_of: dict | None = None, embed_provider=None) -> dict:
    rows, hit_at_k, rr_sum = [], 0, 0.0
    for item in gold:
        results = hybrid.search(bm25, graph, item["query"], k=k, type_of=type_of,
                                embed_provider=embed_provider)
        ranked = [n for n, _, _ in results]
        rel = set(item["relevant"])
        if not rel:
            # 정답이 볼트에 없는 질의 — 확신 있는 답변만 실패(공백/약함 경고면 성공)
            top = results[0][1] if results else 0.0
            ratio = top / bm25.ideal_score(item["query"])
            ok = ratio < RATIO_WEAK
            hit_at_k += 1 if ok else 0
            rr_sum += 1.0 if ok else 0.0
            label = "공백✔" if ok else "확신오답✘"
            rows.append({"query": item["query"], "hit": ok, "rank": label,
                         "got": ranked, "want": ["(볼트에 없음 — 비확신 기대)"]})
            continue
        found = [n for n in ranked if n in rel]
        rank = next((i + 1 for i, n in enumerate(ranked) if n in rel), None)
        hit_at_k += 1 if found else 0
        rr_sum += 1.0 / rank if rank else 0.0
        rows.append({"query": item["query"], "hit": bool(found), "rank": rank,
                     "got": ranked, "want": sorted(rel)})
    n = max(len(gold), 1)
    return {"recall_at_k": hit_at_k / n, "mrr": rr_sum / n, "k": k, "n": n, "rows": rows}


def to_markdown(res: dict) -> str:
    L = [f"# 검색 품질 평가 (골드셋 {res['n']}건, k={res['k']})", "",
         f"- **Recall@{res['k']} = {res['recall_at_k']:.1%}** · **MRR = {res['mrr']:.3f}**", "",
         "| 질의 | 적중 | 정답 순위 |", "|---|---|---|"]
    for r in res["rows"]:
        L.append(f"| {r['query']} | {'✅' if r['hit'] else '❌'} | {r['rank'] or '-'} |")
    L += ["", "> 실패 케이스는 골드셋이 틀렸는지(노트명 변경 등) · 검색이 틀렸는지 사람이 판정한다."]
    return "\n".join(L) + "\n"
