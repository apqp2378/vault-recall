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


def test_ideal_score_positive():
    _, _, bm25 = load()
    assert bm25.ideal_score("퍼널 병목") > 0


def test_confidence_levels():
    notes, graph, bm25 = load()
    known = recall.perform(notes, graph, bm25, "퍼널 분석 병목")
    unknown = recall.perform(notes, graph, bm25, "양자컴퓨터 오류정정 큐비트")
    assert known.confidence == "충분" and known.ratio > unknown.ratio
    assert unknown.confidence == "공백" and unknown.gap


def test_moc_penalty_demotes_hub():
    notes, graph, bm25 = load()
    type_of = {n.name: n.type for n in notes.values()}
    plain = [n for n, _, _ in hybrid.search(bm25, graph, "분석 기법", k=3)]
    penal = [n for n, _, _ in hybrid.search(bm25, graph, "분석 기법", k=3, type_of=type_of)]
    def moc_rank(names):
        return next((i for i, n in enumerate(names) if n.startswith("MOC_")), 99)
    assert moc_rank(penal) >= moc_rank(plain)  # 패널티가 MOC 순위를 올리지는 않는다


def test_eval_empty_relevant_expects_nonconfident(tmp_path):
    import json as _json
    notes, graph, bm25 = load()
    gold_file = tmp_path / "g.json"
    gold_file.write_text(_json.dumps(
        [{"query": "양자컴퓨터 오류정정 큐비트", "relevant": []}], ensure_ascii=False),
        encoding="utf-8")
    gold = evalkit.load_gold(gold_file, list(notes))
    res = evalkit.evaluate(bm25, graph, gold, k=5,
                           type_of={n.name: n.type for n in notes.values()})
    assert res["recall_at_k"] == 1.0  # 볼트에 없는 주제 → 비확신 처리 = 성공


def test_embed_prefix_and_digest():
    from vault_recall.search.embed import needs_e5_prefix, corpus_digest, get_provider
    assert needs_e5_prefix("intfloat/multilingual-e5-small")
    assert not needs_e5_prefix("BAAI/bge-m3")
    c1 = {"a": "본문", "b": "다른 본문"}
    assert corpus_digest("m", c1) == corpus_digest("m", dict(reversed(list(c1.items()))))
    assert corpus_digest("m", c1) != corpus_digest("m2", c1)
    assert get_provider(enabled=False) is None
    # 모델을 못 받는 환경에서도 죽지 않고 None 폴백
    assert get_provider(True, "존재하지-않는/모델", quiet=True) is None


def test_sm2_sequence_and_due():
    from datetime import date
    from vault_recall import srs
    e = srs.sm2_update({}, 5, date(2026, 1, 1))
    assert e["interval"] == 1 and e["due"] == "2026-01-02"
    e = srs.sm2_update(e, 5, date(2026, 1, 2))
    assert e["interval"] == 6
    e2 = srs.sm2_update(e, 2, date(2026, 1, 8))   # 실패 → 리셋
    assert e2["interval"] == 1 and e2["reps"] == 0
    assert e2["ef"] >= 1.3


def test_train_due_prioritizes_answer_cards():
    from datetime import date
    from vault_recall import srs
    notes, _, _ = load()
    picks = srs.due_cards(notes, {}, date(2026, 1, 1), n=3)
    assert picks and picks[0][0] in ("답변_퍼널 병목", "퍼널 개선 경험")


def test_ingest_files_md_and_missing_docling(tmp_path):
    src = tmp_path / "docs"; src.mkdir()
    (src / "메모.md").write_text("# 첫 줄 요약\n본문입니다", encoding="utf-8")
    (src / "슬라이드.pptx").write_bytes(b"fake")
    created, skipped = ingest.run_files(src, tmp_path)
    assert created == ["메모.md"]
    card = (tmp_path / "90_inbox" / "메모.md").read_text(encoding="utf-8")
    assert "verified: false" in card and "본문입니다" in card
    assert any("docling" in s for s in skipped)


def test_reranker_pipeline_with_fake():
    notes, graph, bm25 = load()
    class FakeReranker:
        def rerank(self, q, cands, k=5):
            return [(n, 1.0) for n, _ in reversed(cands)][:k]  # 순서 뒤집기
    texts = {n.name: n.search_text() for n in notes.values()}
    base = [n for n, _, _ in hybrid.search(bm25, graph, "퍼널", k=3)]
    rer = [n for n, _, _ in hybrid.search(bm25, graph, "퍼널", k=3,
                                          reranker=FakeReranker(), texts=texts)]
    assert base != rer  # 리랭커가 순위에 실제로 개입


def test_report_highlight(tmp_path):
    from vault_recall import report as report_mod
    notes, graph, _ = load()
    out = tmp_path / "g.html"
    report_mod.build(notes, graph, out, highlight={"퍼널 분석 기초"}, highlight_label="테스트")
    html = out.read_text(encoding="utf-8")
    assert "#ff3b30" in html and "소환 근거 하이라이트" in html


def test_lint_invalid_values(tmp_path):
    from vault_recall.parser import load_vault as lv, lint as lint_fn
    (tmp_path / "나쁜 노트.md").write_text(
        "---\ntype: 이상한값\nverified: maybe\npriority: ★★x\ndescription: d\n---\n본문",
        encoding="utf-8")
    issues = lint_fn(lv(tmp_path))
    kinds = {(k) for _, k, *_ in issues["invalid_values"]}
    assert {"type", "verified", "priority"} <= kinds
