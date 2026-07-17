# -*- coding: utf-8 -*-
"""vault-recall 핵심 동작 테스트 — demo_vault 기준(결정적)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vault_recall.parser import load_vault, lint, parse_frontmatter
from vault_recall.graph import Graph
from vault_recall.search.bm25 import BM25, tokenize
from vault_recall.search import hybrid
from vault_recall import recall, evalkit, ingest

VAULT = ROOT / "demo_vault"


def load():
    notes = load_vault(VAULT)
    graph = Graph(notes)
    bm25 = BM25().fit({n.name: n.search_text() for n in notes.values()})
    return notes, graph, bm25


def test_parse_frontmatter():
    meta, body = parse_frontmatter("---\ntype: tool\nverified: true\ntags: [a, b]\n---\n본문")
    assert meta["type"] == "tool" and meta["tags"] == ["a", "b"] and "본문" in body


def test_load_vault_and_links():
    notes, graph, _ = load()
    assert len(notes) == 12
    assert "퍼널 분석 기초" in notes["퍼널 개선 경험"].outlinks


def test_lint_clean_demo():
    notes, _, _ = load()
    issues = lint(notes)
    assert issues["broken_links"] == []


def test_tokenize_korean_bigram():
    toks = tokenize("퍼널 분석")
    assert "퍼널" in toks and "분석" in toks and "퍼널"[0:2] in toks


def test_bm25_ranks_relevant_first():
    notes, _, bm25 = load()
    top = bm25.query("퍼널 병목", k=3)
    assert top and "퍼널" in top[0][0]


def test_graph_orphan_detection():
    notes, graph, _ = load()
    assert "고아 노트 예시" in graph.orphans()


def test_hybrid_graph_boost_pulls_neighbors():
    notes, graph, bm25 = load()
    ranked = hybrid.search(bm25, graph, "퍼널 분석", k=6)
    names = [n for n, _, _ in ranked]
    # 직접 매칭 노트의 이웃(MOC_분석 기법)이 근거 후보로 확장돼야 한다
    assert "MOC_분석 기법" in names


def test_recall_verified_only_filters():
    notes, graph, bm25 = load()
    res = recall.perform(notes, graph, bm25, "검증 전 아이디어", verified_only=True)
    assert all(note.verified for note, _, _ in res.hits)


def test_recall_honest_gap_on_unknown_topic():
    notes, graph, bm25 = load()
    res = recall.perform(notes, graph, bm25, "양자컴퓨터 오류정정 큐비트")
    assert res.gap  # 볼트에 없는 주제 → 지어내지 않고 공백 선언
    assert res.uncovered


def test_eval_metrics():
    notes, graph, bm25 = load()
    gold = evalkit.load_gold(ROOT / "eval" / "gold_demo.json", list(notes))
    res = evalkit.evaluate(bm25, graph, gold, k=5)
    assert res["recall_at_k"] >= 0.8   # 데모 볼트에선 높아야 정상
    assert 0.0 <= res["mrr"] <= 1.0


def test_ingest_creates_inbox_cards(tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("https://github.com/pgvector/pgvector\nhttps://youtu.be/abc123\n",
                    encoding="utf-8")
    created = ingest.run(urls, tmp_path)
    assert len(created) == 2
    card = (tmp_path / "90_inbox" / created[0]).read_text(encoding="utf-8")
    assert "verified: false" in card and "type: tool" in card
