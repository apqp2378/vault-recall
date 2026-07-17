#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""noton→vault 증분 동기화 — 노션 Career-Ops의 새/수정 항목을 볼트 카드로 반영.

이 스크립트는 사용자 PC에서 직접 실행한다(예약 자동화는 클라우드라 로컬 볼트에 못 닿음).
Notion 공식 API(data sources, 2025-09-03)를 표준 라이브러리(urllib)로 호출 — 외부 의존성 0.

동작:
  - 6개 데이터소스를 페이지네이션으로 조회
  - 각 페이지 id를 frontmatter `notion_id`로 남겨 **중복 없이** 관리
  - 새 페이지 → 해당 폴더에 카드 생성(type·tags·link·description·verified 매핑)
  - 수정된 페이지 → 사람이 큐레이션한 원본은 건드리지 않고, 90_inbox/_updates/에
    "[UPDATED] 제목" 초안을 떨궈 사람이 병합하게 함 (HITL — 자동 덮어쓰기 금지)
  - 상태(.recall_cache/notion_sync_state.json)에 페이지별 last_edited_time 저장 → 증분

사용:
  1) 노션 통합(integration) 생성 → 토큰 발급 → 6개 DB를 그 통합과 공유
     https://www.notion.so/my-integrations
  2) 환경변수로 토큰 지정:  export NOTION_TOKEN=secret_xxx   (Windows: set NOTION_TOKEN=...)
  3) python scripts/sync_notion.py --vault "C:/Users/최상원/career-vault"
     옵션: --dry-run(쓰지 않고 미리보기)  --token secret_xxx(env 대신)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NOTION_VERSION = os.environ.get("NOTION_VERSION", "2025-09-03")

# 데이터소스 id → 볼트 배치 규칙 (id는 노션 collection UUID = data source id)
SOURCES = {
    "baeaeeaa-e97d-4bba-b5bf-65ffaa56d8c4": {"name": "유튜브 학습노트", "folder": "20_학습", "type": "learning"},
    "e7e2d239-8120-429d-b52c-398d83a17e7c": {"name": "Bullet Bank",   "folder": "10_경험", "type": "experience"},
    "5d8aba84-e902-4589-ae7e-87e468e00129": {"name": "실무 트렌드",    "folder": "30_트렌드", "type": "trend"},
    "e19c34c0-5ffd-47a4-86d6-91b4f0760e3d": {"name": "GitHub 레포",    "folder": "40_도구",  "type": "tool"},
    "2aa40554-cd98-4d04-8e9e-dc72b0e4ec12": {"name": "JD Inbox",      "folder": "50_지원",  "type": "job"},
    "2dec316d-42f6-47e2-a66f-64f5f88ce324": {"name": "Daily Log",     "folder": "60_작업일지", "type": "log"},
}

# 노션 속성명 → 볼트 필드 (있는 것 먼저 채택)
DESC_KEYS = ["한줄요약", "한 줄 요약", "description", "Bullet 문장", "직무", "제목"]
PRIORITY_KEYS = ["우선순위", "priority"]
VERIFIED_KEYS = ["검증상태", "검증 상태"]
LINK_KEYS = ["링크", "url", "출처 URL", "원문 링크", "최종 산출물"]
TAG_KEYS = ["카테고리", "도메인", "매칭 토픽", "적용 대상"]
APPLY_KEYS = ["본인적용", "본인 적용", "이번 주 적용 1건", "면접 활용 포인트"]
VERIFIED_TRUE = {"검증완료", "이력서반영"}


# ────────────────────────── 노션 속성 추출 (제너릭) ──────────────────────────
def prop_text(prop: dict) -> str:
    """단일 속성 → 사람이 읽는 문자열 (title/rich_text/select/multi_select/url/number/checkbox/date)."""
    t = prop.get("type")
    v = prop.get(t)
    if v is None:
        return ""
    if t in ("title", "rich_text"):
        return "".join(seg.get("plain_text", "") for seg in v).strip()
    if t == "select":
        return v.get("name", "") if v else ""
    if t == "multi_select":
        return ", ".join(o.get("name", "") for o in v)
    if t in ("url", "email", "phone_number"):
        return v or ""
    if t == "number":
        return str(v) if v is not None else ""
    if t == "checkbox":
        return "예" if v else "아니오"
    if t == "date":
        return (v or {}).get("start", "") or ""
    if t in ("created_time", "last_edited_time"):
        return v or ""
    if t == "formula":
        return prop_text({"type": v.get("type"), v.get("type"): v.get(v.get("type"))}) if v else ""
    return ""


def find_prop(props: dict, keys: list[str]) -> str:
    for k in keys:
        if k in props:
            val = prop_text(props[k])
            if val:
                return val
    return ""


def title_of(props: dict) -> str:
    for name, p in props.items():
        if p.get("type") == "title":
            return prop_text(p) or "(무제)"
    return "(무제)"


def tags_of(props: dict, extra: str) -> list[str]:
    tags = ["synced", extra]
    for k in TAG_KEYS:
        if k in props:
            val = prop_text(props[k])
            if val:
                tags.append(val.split()[0] if val.startswith("#") else val)
    # 중복 제거, 순서 유지
    seen, out = set(), []
    for t in tags:
        t = t.strip()
        if t and t not in seen:
            seen.add(t); out.append(t)
    return out


def safe_name(title: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', " ", title)
    return re.sub(r"\s+", " ", s).strip()[:80] or "untitled"


def build_card(page: dict, src: dict, today: str) -> tuple[str, str]:
    """노션 page → (파일명, 카드 마크다운). verified:false 초안(사람 검증 대기)."""
    props = page.get("properties", {})
    title = title_of(props)
    desc = find_prop(props, DESC_KEYS)
    priority = find_prop(props, PRIORITY_KEYS)
    verified = find_prop(props, VERIFIED_KEYS) in VERIFIED_TRUE
    link = find_prop(props, LINK_KEYS)
    apply_txt = find_prop(props, APPLY_KEYS)

    fm = ["---",
          f"notion_id: {page['id']}",
          f"type: {src['type']}",
          f"verified: {'true' if verified else 'false'}"]
    if priority:
        fm.append(f"priority: {priority}")
    fm.append(f"tags: [{', '.join(tags_of(props, src['name']))}]")
    fm.append(f"source: Notion · {src['name']}")
    if link:
        fm.append(f"link: {link}")
    if desc:
        fm.append(f"description: {desc[:120]}")
    fm.append(f"synced: {today}")
    fm.append("---")

    body = [""]
    if desc:
        body.append(desc)
    if apply_txt:
        body += ["", "## 본인 적용", apply_txt]
    body += ["", "## 연결", "- [[]]"]   # 링크는 사람/AI 큐레이션 단계 (diagnose가 orphan으로 잡아줌)
    return safe_name(title), "\n".join(fm + body) + "\n"


# ────────────────────────── 노션 API (urllib) ──────────────────────────
def notion_query(ds_id: str, token: str, cursor: str | None) -> dict:
    """data source 1페이지 조회. 최신 API(2025-09-03) 실패 시 구 databases 엔드포인트로 폴백."""
    body = {"page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    payload = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION,
               "Content-Type": "application/json"}
    for url in (f"https://api.notion.com/v1/data_sources/{ds_id}/query",
                f"https://api.notion.com/v1/databases/{ds_id}/query"):
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404) and "data_sources" in url:
                continue  # 구버전 워크스페이스 → databases 엔드포인트 재시도
            raise SystemExit(f"[오류] 노션 API {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    raise SystemExit("[오류] data_sources·databases 엔드포인트 모두 실패")


def iter_pages(ds_id: str, token: str):
    cursor = None
    while True:
        data = notion_query(ds_id, token, cursor)
        for pg in data.get("results", []):
            yield pg
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")


# ────────────────────────── 볼트 상태 ──────────────────────────
def existing_notion_ids(vault: Path) -> set[str]:
    """볼트 전체에서 이미 있는 notion_id 수집 (중복 생성 방지)."""
    ids = set()
    for p in vault.rglob("*.md"):
        if any(part.startswith(".") for part in p.relative_to(vault).parts):
            continue
        head = p.read_text(encoding="utf-8", errors="replace")[:300]
        m = re.search(r"^notion_id:\s*(\S+)", head, re.M)
        if m:
            ids.add(m.group(1))
    return ids


def load_state(vault: Path) -> dict:
    p = vault / ".recall_cache" / "notion_sync_state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(vault: Path, state: dict) -> None:
    p = vault / ".recall_cache" / "notion_sync_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def write_card(folder: Path, fname: str, text: str) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (fname + ".md")
    i = 2
    while dest.exists():
        dest = folder / (f"{fname} ·{i}.md"); i += 1
    dest.write_text(text, encoding="utf-8")
    return dest.name


# ────────────────────────── main ──────────────────────────
def sync(vault: Path, token: str, dry_run: bool = False, baseline: bool = False) -> dict:
    state = load_state(vault)
    # 이미 반영된 것 = 상태파일에 기록된 페이지 + 볼트에 notion_id로 박힌 페이지
    known = set(state) | existing_notion_ids(vault)
    created, updated, skipped, based = [], [], 0, 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for ds_id, src in SOURCES.items():
        for page in iter_pages(ds_id, token):
            pid = page["id"]
            edited = page.get("last_edited_time", "")
            if baseline:
                # 카드 생성 없이 '이미 반영됨'으로만 표시 (최초 1회 기준선)
                state[pid] = edited
                based += 1
                continue
            fname, text = build_card(page, src, today)
            if pid not in known:
                if not dry_run:
                    written = write_card(vault / src["folder"], fname, text)
                else:
                    written = fname + ".md"
                created.append(f"{src['folder']}/{written}")
                state[pid] = edited
            elif state.get(pid) and edited and edited > state[pid]:
                # 수정됨 — 큐레이션 원본은 안 건드리고 검토용 초안만 남김
                if not dry_run:
                    write_card(vault / "90_inbox" / "_updates", f"[UPDATED] {fname}", text)
                updated.append(f"{src['name']} · {fname}")
                state[pid] = edited
            else:
                skipped += 1

    if not dry_run:
        save_state(vault, state)
    return {"created": created, "updated": updated, "skipped": skipped, "baseline": based}


def main(argv=None):
    ap = argparse.ArgumentParser(description="노션 Career-Ops → 볼트 증분 동기화")
    ap.add_argument("--vault", required=True, help="볼트 폴더 경로")
    ap.add_argument("--token", default=os.environ.get("NOTION_TOKEN"),
                    help="노션 통합 토큰 (기본: 환경변수 NOTION_TOKEN)")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 미리보기")
    ap.add_argument("--baseline", action="store_true",
                    help="최초 1회: 현재 노션 항목 전체를 '이미 반영됨'으로 표시(카드 생성 안 함). 이후 새 항목만 동기화.")
    a = ap.parse_args(argv)
    if not a.token:
        sys.exit("[오류] NOTION_TOKEN이 없습니다. 환경변수로 설정하거나 --token 지정. "
                 "토큰 발급: https://www.notion.so/my-integrations (6개 DB를 통합과 공유 필수)")
    if ("..." in a.token) or ("토큰" in a.token) or (not a.token.isascii()):
        sys.exit("[오류] 예시 문구('ntn_...토큰...')를 그대로 쓴 것 같습니다. "
                 "노션에서 복사한 진짜 토큰(ntn_ 뒤에 영문·숫자로만 된 긴 문자열)을 넣으세요.\n"
                 "  예)  export NOTION_TOKEN=ntn_1a2B3c...   (한글·따옴표·... 금지)")
    vault = Path(a.vault).expanduser()
    if not vault.exists():
        sys.exit(f"[오류] 볼트 폴더 없음: {vault}")

    r = sync(vault, a.token, dry_run=a.dry_run, baseline=a.baseline)
    tag = "[미리보기] " if a.dry_run else ""
    if a.baseline:
        print(f"{tag}기준선 설정 완료 — 현재 {r['baseline']}개를 '이미 반영됨'으로 표시(카드 생성 안 함). "
              f"이후 실행부터 새/수정 항목만 동기화됩니다.")
        return
    print(f"{tag}동기화 완료 — 새 카드 {len(r['created'])} · 수정 알림 {len(r['updated'])} · 변화없음 {r['skipped']}")
    for c in r["created"][:30]:
        print("  + ", c)
    for u in r["updated"][:15]:
        print("  ~ ", u, "→ 90_inbox/_updates/ (사람이 병합)")
    if r["created"] or r["updated"]:
        print("\n다음: 새 카드는 `verified:false` 초안입니다. 검토·검증·링크 후 사용하세요.")
        print("      `vault-recall diagnose <vault>`로 새 orphan(미연결) 카드를 확인하고 연결하세요.")


if __name__ == "__main__":
    main()
