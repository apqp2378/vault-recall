"""볼트 진단 — 소환 가능성 관점의 위생 리포트 + 연결 보강 우선순위.

knowledge-ops의 orphan 진단을 계승·강화:
- orphan(소환 불가) 목록 + 각 orphan의 '가장 가까운 허브(MOC)' 자동 제안 ← 연결 액션까지
- 폴더별 검증률(verified) — 어떤 지식이 아직 '믿고 쓸 수 없는' 상태인지
- 중복 후보(동일 원문 링크)
모든 진단은 "그래서 무슨 결정"으로 끝난다.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .parser import Note
from .search.bm25 import BM25


def run(notes: dict[str, Note], graph, bm25: BM25) -> str:
    total = len(notes)
    orphans = graph.orphans()
    hubs = graph.hubs(10)
    comps = graph.components()

    # 폴더별 검증률
    folder_stat = defaultdict(lambda: [0, 0])   # folder → [verified, total]
    for n in notes.values():
        folder_stat[n.folder][1] += 1
        if n.verified:
            folder_stat[n.folder][0] += 1

    # 중복 후보: 같은 외부 link를 가리키는 노트들
    by_link = defaultdict(list)
    for n in notes.values():
        link = str(n.meta.get("link", "")).strip()
        if link:
            by_link[link].append(n.name)
    dups = {l: ns for l, ns in by_link.items() if len(ns) > 1}

    # orphan → 가장 가까운 MOC 제안 (BM25로 MOC 유사도)
    mocs = [n for n in notes if n.startswith("MOC_")]
    moc_bm = BM25().fit({m: notes[m].search_text() for m in mocs}) if mocs else None
    suggestions = []
    for o in orphans[:15]:
        target = "-"
        if moc_bm:
            r = moc_bm.query(notes[o].search_text(), k=1)
            if r:
                target = r[0][0]
        suggestions.append((o, target))

    L = ["# 볼트 진단 — 소환 가능성 리포트", ""]
    L.append(f"- 노트 {total}개 · 컴포넌트 {len(comps)}개(최대 {len(comps[0]) if comps else 0}) "
             f"· **orphan {len(orphans)}개 ({len(orphans)/max(total,1):.1%})**")
    ver_all = sum(1 for n in notes.values() if n.verified)
    L.append(f"- 검증(verified) {ver_all}/{total} ({ver_all/max(total,1):.1%}) — 미검증 지식은 소환돼도 결론에 못 쓴다")
    L.append("")
    L.append("## 허브 Top 10 (소환의 관문)")
    for h in hubs:
        L.append(f"- [[{h}]] — 연결 {graph.degree(h)}")
    L.append("")
    L.append("## 폴더별 검증률")
    for f, (v, t) in sorted(folder_stat.items()):
        L.append(f"- {f}: {v}/{t} ({v/max(t,1):.0%})")
    L.append("")
    if orphans:
        L.append("## 결정: orphan 연결 보강 우선순위")
        L.append("orphan은 그래프에서 소환되지 않는 지식이다. 아래 제안 MOC에 링크 1개만 걸어도 소환권 안으로 들어온다.")
        for o, target in suggestions:
            L.append(f"- [[{o}]] → 제안: [[{target}]]")
    else:
        L.append("## 결정: orphan 0 — 전 노트가 소환권 안에 있다. 다음 과제는 미검증 노트의 검증 전환.")
    if dups:
        L.append("")
        L.append("## 중복 후보 (같은 원문 링크) — '한 자료 한 자리' 위반 검토")
        for l, ns in list(dups.items())[:10]:
            L.append(f"- {l} ← {', '.join(ns)}")
    return "\n".join(L) + "\n"
