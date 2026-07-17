"""간격반복 훈련 스케줄러 — SM-2 (결정적).

ts-fsrs(FSRS, SM-2의 후계)의 개념을 반영: '소환되게 저장'에서 '기억되게 훈련'으로.
루프의 마지막 단계 — 수집→구조화→소환→진단→증빙→**훈련**.

- 알고리즘: SM-2 (결정적·검증 용이). FSRS 업그레이드 경로는 provider 교체로 열어둠.
- 훈련 이력: <vault>/.recall_cache/srs_log.json (사람이 읽을 수 있는 JSON).
- 오늘의 카드 선정(결정적 우선순위):
  ① 복습 기한(due)이 지난 카드 (기한 오래된 순)
  ② 한 번도 훈련 안 한 카드 — answer(답변카드)·experience(경험) 먼저, 다음 verified 순
- 판정은 사람: grade 0~5를 사용자가 매긴다 (AI가 채점하지 않는다).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

TRAIN_FIRST_TYPES = ("answer", "experience")   # 면접 대비 가치가 높은 카드 우선


def _log_path(vault: str | Path) -> Path:
    p = Path(vault) / ".recall_cache" / "srs_log.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_log(vault) -> dict:
    p = _log_path(vault)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_log(vault, log: dict) -> None:
    _log_path(vault).write_text(json.dumps(log, ensure_ascii=False, indent=1),
                                encoding="utf-8")


def sm2_update(entry: dict, grade: int, today: date) -> dict:
    """SM-2 한 스텝. grade 0~5 (3 미만 = 실패 → 처음부터)."""
    grade = max(0, min(5, int(grade)))
    reps = entry.get("reps", 0)
    ef = entry.get("ef", 2.5)
    interval = entry.get("interval", 0)
    if grade >= 3:
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = round(interval * ef)
        reps += 1
    else:
        reps, interval = 0, 1
    ef = max(1.3, ef + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)))
    return {"reps": reps, "ef": round(ef, 3), "interval": interval,
            "last": today.isoformat(), "due": (today + timedelta(days=interval)).isoformat(),
            "history": entry.get("history", []) + [{"date": today.isoformat(), "grade": grade}]}


def due_cards(notes: dict, log: dict, today: date, n: int = 5) -> list[tuple[str, str]]:
    """→ [(노트명, 사유)] 오늘 훈련할 카드 n개 (결정적)."""
    trainable = [name for name, note in notes.items()
                 if note.type in ("answer", "experience", "learning", "principle")]
    overdue = sorted(
        [(name, log[name]["due"]) for name in trainable
         if name in log and log[name]["due"] <= today.isoformat()],
        key=lambda x: (x[1], x[0]))
    picks = [(name, f"복습 기한 {due}") for name, due in overdue[:n]]
    if len(picks) < n:
        fresh = [name for name in trainable if name not in log]
        fresh.sort(key=lambda name: (
            0 if notes[name].type in TRAIN_FIRST_TYPES else 1,
            0 if notes[name].verified else 1,
            name))
        picks += [(name, "첫 훈련 (미훈련 카드)") for name in fresh[:n - len(picks)]]
    return picks


def render_session(notes: dict, picks: list[tuple[str, str]]) -> str:
    """훈련 세션 안내 — 카드 앞면(질문/제목)만 보여주고 먼저 답하게 한다."""
    L = ["# 오늘의 되새김 훈련", "",
         "카드를 보기 전에 **먼저 소리 내어 답해보고**, 노트를 열어 스스로 판정한 뒤 grade를 기록:",
         '`vault-recall train <vault> --grade "<카드명>" <0~5>`',
         "(5=완벽 회상 · 4=머뭇 후 정답 · 3=간신히 · 2이하=실패)", ""]
    for i, (name, reason) in enumerate(picks, 1):
        note = notes[name]
        L.append(f"## {i}. [[{name}]]  — {reason}")
        q = note.description or "(요약 없음 — 노트 제목만 보고 내용을 떠올려 보라)"
        L.append(f"> Q: {q}")
        L.append("")
    if not picks:
        L.append("오늘 훈련할 카드가 없다. (모든 카드가 기한 전)")
    return "\n".join(L)
