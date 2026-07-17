# -*- coding: utf-8 -*-
"""noton→vault 동기화 로직 테스트 (HTTP 제외 — API 호출은 iter_pages 목킹)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("syncmod", ROOT / "scripts" / "sync_notion.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def _page(pid, title, verified="검증완료", edited="2026-07-17T00:00:00Z"):
    return {"id": pid, "last_edited_time": edited, "properties": {
        "제목": {"type": "title", "title": [{"plain_text": title}]},
        "한줄요약": {"type": "rich_text", "rich_text": [{"plain_text": title + " 요약"}]},
        "검증상태": {"type": "select", "select": {"name": verified}},
        "우선순위": {"type": "select", "select": {"name": "★★★"}},
        "링크": {"type": "url", "url": "https://x/" + pid},
    }}


def test_build_card_maps_fields():
    src = {"name": "유튜브 학습노트", "folder": "20_학습", "type": "learning"}
    fname, card = sync.build_card(_page("p1", "RAG 기초"), src, "2026-07-17")
    assert "RAG 기초" in fname
    assert "notion_id: p1" in card and "type: learning" in card
    assert "verified: true" in card and "priority: ★★★" in card
    assert "link: https://x/p1" in card and "synced: 2026-07-17" in card


def test_verified_false_for_unreviewed():
    _, card = sync.build_card(_page("p2", "미검증건", verified="신규"),
                              {"name": "JD Inbox", "folder": "50_지원", "type": "job"}, "2026-07-17")
    assert "verified: false" in card


def test_multiselect_tags():
    pg = _page("p3", "태그건")
    pg["properties"]["매칭 토픽"] = {"type": "multi_select",
                                  "multi_select": [{"name": "이커머스"}, {"name": "그로스"}]}
    _, card = sync.build_card(pg, {"name": "JD Inbox", "folder": "50_지원", "type": "job"}, "2026-07-17")
    assert "이커머스" in card and "그로스" in card


def test_incremental_dedup_and_update(tmp_path, monkeypatch):
    (tmp_path / "20_학습").mkdir()
    # 이미 큐레이션된 카드(같은 notion_id) → 재생성 안 함
    (tmp_path / "20_학습" / "기존.md").write_text(
        "---\nnotion_id: old-1\ntype: learning\nverified: true\n---\n큐레이션됨\n", encoding="utf-8")

    pages = [_page("old-1", "기존건"), _page("new-1", "신규건")]
    monkeypatch.setattr(sync, "iter_pages",
                        lambda ds, t: iter(pages if ds.startswith("baeaeeaa") else []))

    r1 = sync.sync(tmp_path, token="fake")
    assert len(r1["created"]) == 1 and r1["skipped"] == 1        # new-1만 생성, old-1 skip
    r2 = sync.sync(tmp_path, token="fake")
    assert len(r2["created"]) == 0                               # idempotent

    # 수정 감지 → 90_inbox/_updates 초안
    monkeypatch.setattr(sync, "iter_pages",
                        lambda ds, t: iter([_page("new-1", "신규건", edited="2026-07-20T00:00:00Z")]
                                           if ds.startswith("baeaeeaa") else []))
    r3 = sync.sync(tmp_path, token="fake")
    assert len(r3["updated"]) == 1
    assert (tmp_path / "90_inbox" / "_updates").exists()


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "iter_pages",
                        lambda ds, t: iter([_page("z1", "드라이런")] if ds.startswith("baeaeeaa") else []))
    r = sync.sync(tmp_path, token="fake", dry_run=True)
    assert len(r["created"]) == 1
    assert not (tmp_path / "20_학습").exists()   # 실제 파일 없음
