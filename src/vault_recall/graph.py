"""지식그래프 — 실제 위키링크가 엣지 (knowledge-ops의 'topic 공유 근사'를 대체).

모든 지표는 결정적 계산. 절대 점수가 아니라 상대 비교·의사결정 보조.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .parser import Note


class Graph:
    def __init__(self, notes: dict[str, Note]):
        self.notes = notes
        self.out = defaultdict(set)
        self.inc = defaultdict(set)
        for n in notes.values():
            for l in n.outlinks:
                if l in notes and l != n.name:
                    self.out[n.name].add(l)
                    self.inc[l].add(n.name)

    def neighbors(self, name: str) -> set:
        return self.out.get(name, set()) | self.inc.get(name, set())

    def degree(self, name: str) -> int:
        return len(self.neighbors(name))

    def orphans(self) -> list:
        """들어오는 링크도 나가는 링크도 없는 노트 = 소환 불가 지식."""
        return sorted(n for n in self.notes if self.degree(n) == 0)

    def hubs(self, k: int = 10) -> list:
        return sorted(self.notes, key=lambda n: -self.degree(n))[:k]

    def components(self) -> list[set]:
        seen, comps = set(), []
        for start in self.notes:
            if start in seen:
                continue
            comp, stack = set(), [start]
            while stack:
                cur = stack.pop()
                if cur in comp:
                    continue
                comp.add(cur)
                stack.extend(self.neighbors(cur) - comp)
            seen |= comp
            comps.append(comp)
        return sorted(comps, key=len, reverse=True)

    def export_csv(self, outdir: str | Path) -> None:
        """재현 가능성: 노드·엣지 외부화 (knowledge-ops 전통 계승)."""
        outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / "nodes.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "folder", "type", "verified", "degree", "description"])
            for n in self.notes.values():
                w.writerow([n.name, n.folder, n.type, n.verified, self.degree(n.name), n.description])
        with open(outdir / "edges.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["source", "target"])
            for s, targets in sorted(self.out.items()):
                for t in sorted(targets):
                    w.writerow([s, t])
