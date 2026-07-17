"""외부 자료 수집 → 90_inbox 카드 초안 (topic-shelf의 역할 계승, 소스 중립).

URL 목록(txt, 1줄 1URL) → frontmatter 스캐폴드가 붙은 inbox 카드 생성.
- 결정적: 네트워크 접근 없음. 제목은 URL 슬러그에서 유도, 사람이 다듬는다.
- HITL: verified: false 로 생성 — 분류·연결·검증은 사람(또는 상위 AI 세션 + 승인).
LLM 요약·본문 수집은 provider 확장점(topic-shelf 패턴)으로 남긴다.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

TYPE_BY_DOMAIN = [("github.com", "tool"), ("youtube.com", "learning"), ("youtu.be", "learning")]


def slug_to_title(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path.strip("/")
    if parsed.netloc.endswith("github.com") and path:
        return path.split("/")[-1] or path
    tail = path.split("/")[-1] if path else parsed.netloc
    tail = re.sub(r"[-_+]", " ", tail).strip() or parsed.netloc
    return tail[:60]


def guess_type(url: str) -> str:
    host = urlparse(url).netloc
    for dom, t in TYPE_BY_DOMAIN:
        if dom in host:
            return t
    return "trend"


def card_text(url: str) -> str:
    return "\n".join([
        "---",
        "type: " + guess_type(url),
        "verified: false",
        "tags: [inbox]",
        "source: ingest",
        "link: " + url.strip(),
        "description: (사람이 채울 것 — 한 줄 요약)",
        "---",
        "",
        "⚠ 자동 생성 초안. 요약·분류·연결 후 폴더로 이동한다.",
        "",
        "## 연결",
        "- [[]]",
    ])


def run(url_file: str | Path, vault_root: str | Path) -> list[str]:
    inbox = Path(vault_root) / "90_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    created = []
    for line in Path(url_file).read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        title = slug_to_title(url)
        safe = re.sub(r'[\\/:*?"<>|]', " ", title).strip()[:80] or "untitled"
        dest = inbox / (safe + ".md")
        i = 2
        while dest.exists():
            dest = inbox / (safe + " ·" + str(i) + ".md")
            i += 1
        dest.write_text(card_text(url), encoding="utf-8")
        created.append(dest.name)
    return created
