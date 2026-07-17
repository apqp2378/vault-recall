"""vault-recall CLI.

  vault-recall scan     <vault>                  # 파싱·린트·통계 + 노드/엣지 CSV 외부화
  vault-recall recall   <vault> "질의" [-k 5] [--verified-only] [--embed]
  vault-recall diagnose <vault>                  # 소환 가능성 진단 리포트
  vault-recall eval     <vault> --gold gold.json # 골드셋 Recall@k·MRR
  vault-recall report   <vault> [-o graph.html]  # 인터랙티브 그래프 HTML
  vault-recall ingest   <vault> --urls list.txt  # URL 목록 → inbox 카드
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import diagnose as diag_mod
from . import evalkit, ingest, recall, report
from .graph import Graph
from .parser import lint, load_vault
from .search.bm25 import BM25
from .search.embed import get_provider


def _load(vault):
    notes = load_vault(vault)
    if not notes:
        sys.exit(f"노트가 없습니다: {vault}")
    graph = Graph(notes)
    bm25 = BM25().fit({n.name: n.search_text() for n in notes.values()})
    return notes, graph, bm25


def main(argv=None):
    p = argparse.ArgumentParser(prog="vault-recall",
                                description="Obsidian 볼트를 소환 가능한 지식 엔진으로")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "recall", "diagnose", "eval", "report", "ingest"):
        sp = sub.add_parser(name)
        sp.add_argument("vault")
        if name == "recall":
            sp.add_argument("query")
            sp.add_argument("-k", type=int, default=5)
            sp.add_argument("--verified-only", action="store_true")
            sp.add_argument("--embed", action="store_true")
        if name == "eval":
            sp.add_argument("--gold", required=True)
            sp.add_argument("-k", type=int, default=5)
        if name == "report":
            sp.add_argument("-o", "--out", default="graph.html")
        if name == "ingest":
            sp.add_argument("--urls", required=True)
    a = p.parse_args(argv)

    if a.cmd == "ingest":
        created = ingest.run(a.urls, a.vault)
        print(f"inbox 카드 {len(created)}개 생성:")
        for c in created:
            print(" -", c)
        return

    notes, graph, bm25 = _load(a.vault)

    if a.cmd == "scan":
        issues = lint(notes)
        orphans = graph.orphans()
        outdir = Path("outputs"); outdir.mkdir(exist_ok=True)
        graph.export_csv(outdir)
        print(f"노트 {len(notes)} · 엣지 {sum(len(v) for v in graph.out.values())} "
              f"· orphan {len(orphans)} · 끊긴링크 {len(issues['broken_links'])} "
              f"· 메타누락 {len(issues['missing_meta'])}")
        for b in issues["broken_links"][:10]:
            print("  BROKEN:", b[0], "->", b[1])
        print("외부화: outputs/nodes.csv · outputs/edges.csv")
    elif a.cmd == "recall":
        provider = get_provider(a.embed)
        if provider is not None:
            provider.fit({n.name: n.search_text() for n in notes.values()})
        res = recall.perform(notes, graph, bm25, a.query, k=a.k,
                             verified_only=a.verified_only, embed_provider=provider)
        print(res.to_markdown())
    elif a.cmd == "diagnose":
        print(diag_mod.run(notes, graph, bm25))
    elif a.cmd == "eval":
        gold = evalkit.load_gold(a.gold, list(notes))
        res = evalkit.evaluate(bm25, graph, gold, k=a.k)
        print(evalkit.to_markdown(res))
    elif a.cmd == "report":
        path = report.build(notes, graph, a.out)
        print("그래프 리포트:", path)


if __name__ == "__main__":
    main()
