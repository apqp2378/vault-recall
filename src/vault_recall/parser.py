"""Obsidian 볼트 파서 — 결정적(LLM 무관여).

노트 스키마: frontmatter(id/type/verified/priority/tags/source/link/description)
+ 본문 + [[위키링크]]. 같은 입력 = 같은 출력.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".obsidian", ".trash", ".git", "_templates", "_scripts", "_to_delete"}
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")
FM_LINE = re.compile(r"^([A-Za-z_가-힣][\w가-힣]*):\s*(.*)$")


@dataclass
class Note:
    name: str
    path: str
    folder: str
    body: str = ""
    meta: dict = field(default_factory=dict)
    outlinks: list = field(default_factory=list)

    @property
    def type(self) -> str:
        return str(self.meta.get("type", ""))

    @property
    def verified(self) -> bool:
        return str(self.meta.get("verified", "false")).lower() == "true"

    @property
    def description(self) -> str:
        return str(self.meta.get("description", ""))

    @property
    def tags(self) -> list:
        return self.meta.get("tags", []) if isinstance(self.meta.get("tags"), list) else []

    def search_text(self) -> str:
        """검색용 텍스트 — 제목·요약에 가중(반복)."""
        return " ".join([
            (self.name + " ") * 3,
            (self.description + " ") * 2,
            " ".join(str(t) for t in self.tags),
            str(self.meta.get("source", "")),
            self.body,
        ])


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """단순 YAML 부분집합(key: value, [리스트]) 파서. 볼트 스키마 전용."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].splitlines():
        m = FM_LINE.match(line.strip())
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k] = v
    return meta, parts[2]


def load_vault(root: str | Path) -> dict[str, Note]:
    """볼트 → {노트명: Note}. 숨김/시스템 폴더 제외."""
    root = Path(root)
    notes: dict[str, Note] = {}
    for p in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts[:-1]):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)
        name = p.stem
        folder = p.relative_to(root).parts[0] if len(p.relative_to(root).parts) > 1 else "(루트)"
        notes[name] = Note(name=name, path=str(p), folder=folder, body=body, meta=meta,
                           outlinks=[l.strip() for l in WIKILINK.findall(body)])
    return notes


KNOWN_TYPES = {"principle", "experience", "learning", "trend", "tool",
               "job", "log", "answer", "moc"}


def lint(notes: dict[str, Note]) -> dict:
    """스키마·링크 위생 점검 — 키 존재 + 값 검증 (instructor의 '스키마 강제' 결정적 구현)."""
    broken, missing_meta, invalid = [], [], []
    for n in notes.values():
        for l in n.outlinks:
            if l and l not in notes:
                broken.append((n.name, l))
        if n.name.startswith(("index", "README", "_")):
            continue
        for key in ("type", "verified", "description"):
            if key not in n.meta:
                missing_meta.append((n.name, key))
        if "type" in n.meta and n.meta["type"] not in KNOWN_TYPES:
            invalid.append((n.name, "type", str(n.meta["type"])))
        if str(n.meta.get("verified", "false")).lower() not in ("true", "false"):
            invalid.append((n.name, "verified", str(n.meta.get("verified"))))
        pri = str(n.meta.get("priority", ""))
        if pri and (set(pri) != {"★"} or not 1 <= len(pri) <= 5):
            invalid.append((n.name, "priority", pri))
    return {"broken_links": broken, "missing_meta": missing_meta,
            "invalid_values": invalid}
