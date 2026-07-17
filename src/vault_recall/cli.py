"""vault-recall CLI.

  vault-recall scan     <vault>                  # 파싱·린트·통계 + 노드/엣지 CSV 외부화
  vault-recall recall   <vault> "질의" [-k 5] [--verified-only] [--embed]
  vault-recall diagnose <vault>                  # 소환 가능성 진단 리포트
  vault-recall eval     <vault> --gold gold.json # 골드셋 Recall@k·MRR
  vault-recall report   <vault> [-o graph.html]  # 인터랙티브 그래프 HTML
  vault-recall ingest   <vault> --urls list.txt   # URL 목록 → inbox 카드
  vault-recall ingest   <vault> --files 폴더/파일  # md/txt/pdf/docx → inbox 카드(docling 선택)
  vault-recall train    <vault> [--due 5]          # 간격반복(SM-2) 오늘의 훈련 카드
  vault-recall train    <vault> --grade "카드" 4   # 회상 판정 기록(사람이 채점)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import diagnose as diag_mod
from . import evalkit, ingest, recall, report, srs
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
    for name in ("scan", "recall", "diagnose", "eval", "report", "ingest", "train"):
        sp = sub.add_parser(name)
        sp.add_argument("vault")
        if name == "recall":
            sp.add_argument("query")
            sp.add_argument("-k", type=int, default=5)
            sp.add_argument("--verified-only", action="store_true")
            sp.add_argument("--no-embed", action="store_true",
                            help="의미 검색 끄기 (기본: 가능하면 자동 활성)")
            sp.add_argument("--model", default=None, help="임베딩 모델명 재정의")
            sp.add_argument("--rerank", action="store_true",
                            help="cross-encoder 리랭커로 상위 후보 재채점")
        if name == "eval":
            sp.add_argument("--gold", required=True)
            sp.add_argument("-k", type=int, default=5)
            sp.add_argument("--embed", action="store_true",
                            help="의미 검색 융합 포함 벤치마크")
            sp.add_argument("--model", default=None)
        if name == "report":
            sp.add_argument("-o", "--out", default="graph.html")
            sp.add_argument("--query", default=None,
                            help="소환 근거를 그래프에 하이라이트")
        if name == "ingest":
            sp.add_argument("--urls")
            sp.add_argument("--files")
        if name == "train":
            sp.add_argument("--due", type=int, default=5)
            sp.add_argument("--grade", nargs=2, metavar=("카드명", "0~5"))
    a = p.parse_args(argv)

    if a.cmd == "ingest":
        if not (a.urls or a.files):
            sys.exit("--urls 또는 --files 중 하나가 필요합니다")
        created, skipped = [], []
        if a.urls:
            created += ingest.run(a.urls, a.vault)
        if a.files:
            c, skipped = ingest.run_files(a.files, a.vault)
            created += c
        print(f"inbox 카드 {len(created)}개 생성:")
        for c in created:
            print(" -", c)
        for s in skipped:
            print(" 스킵:", s)
        return

    notes, graph, bm25 = _load(a.vault)

    if a.cmd == "scan":
        issues = lint(notes)
        orphans = graph.orphans()
        outdir = Path("outputs"); outdir.mkdir(exist_ok=True)
        graph.export_csv(outdir)
        print(f"노트 {len(notes)} · 엣지 {sum(len(v) for v in graph.out.values())} "
              f"· orphan {len(orphans)} · 끊긴링크 {len(issues['broken_links'])} "
              f"· 메타누락 {len(issues['missing_meta'])} "
              f"· 값오류 {len(issues['invalid_values'])}")
        for iv in issues["invalid_values"][:10]:
            print("  INVALID:", iv)
        for b in issues["broken_links"][:10]:
            print("  BROKEN:", b[0], "->", b[1])
        print("외부화: outputs/nodes.csv · outputs/edges.csv")
    elif a.cmd == "recall":
        from .search.embed import DEFAULT_MODEL, get_reranker
        provider = get_provider(enabled=not a.no_embed,
                                model_name=a.model or DEFAULT_MODEL,
                                cache_dir=Path(a.vault) / ".recall_cache")
        if provider is not None:
            provider.fit({n.name: n.search_text() for n in notes.values()})
        reranker = get_reranker(a.rerank)
        res = recall.perform(notes, graph, bm25, a.query, k=a.k,
                             verified_only=a.verified_only, embed_provider=provider,
                             reranker=reranker)
        print(res.to_markdown())
    elif a.cmd == "diagnose":
        print(diag_mod.run(notes, graph, bm25))
    elif a.cmd == "eval":
        gold = evalkit.load_gold(a.gold, list(notes))
        type_of = {n.name: n.type for n in notes.values()}
        provider = None
        if a.embed:
            from .search.embed import DEFAULT_MODEL
            provider = get_provider(True, a.model or DEFAULT_MODEL,
                                    cache_dir=Path(a.vault) / ".recall_cache")
            if provider is not None:
                provider.fit({n.name: n.search_text() for n in notes.values()})
        res = evalkit.evaluate(bm25, graph, gold, k=a.k, type_of=type_of,
                               embed_provider=provider)
        print(evalkit.to_markdown(res))
    elif a.cmd == "report":
        highlight = set()
        if a.query:
            res = recall.perform(notes, graph, bm25, a.query, k=8)
            highlight = {note.name for note, _, _ in res.hits}
        path = report.build(notes, graph, a.out, highlight=highlight,
                            highlight_label=a.query or "")
        print("그래프 리포트:", path,
              f"(하이라이트 {len(highlight)}개)" if highlight else "")
    elif a.cmd == "train":
        from datetime import date
        log = srs.load_log(a.vault)
        if a.grade:
            name, grade = a.grade[0], int(a.grade[1])
            match = notes.get(name) or next(
                (notes[n] for n in notes if name in n), None)
            if match is None:
                sys.exit(f"카드를 찾을 수 없음: {name}")
            log[match.name] = srs.sm2_update(log.get(match.name, {}), grade, date.today())
            srs.save_log(a.vault, log)
            e = log[match.name]
            print(f"기록: [[{match.name}]] grade={grade} → 다음 복습 {e['due']} "
                  f"(간격 {e['interval']}일, EF {e['ef']})")
        else:
            picks = srs.due_cards(notes, log, date.today(), n=a.due)
            print(srs.render_session(notes, picks))


if __name__ == "__main__":
    main()
