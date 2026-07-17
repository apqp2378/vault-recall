# vault-recall

**Obsidian 볼트를 "소환 가능한 지식 엔진"으로 만드는 CLI.**
저장한 지식이 결정의 순간(면접·실무)에 소환되지 않는 문제를, 파싱 → 그래프 → 하이브리드 검색 → 정직한 공백 → 진단 → 정량 평가의 한 루프로 푼다.

> 이 프로젝트는 저자의 두 미완 프로젝트를 하나로 완성한 것이다 —
> **[topic-shelf](https://github.com/apqp2378/topic-shelf)**(외부 자료 수집·큐레이션)는 `ingest`로,
> **[knowledge-ops](https://github.com/apqp2378/knowledge-ops)**(지식그래프 orphan 진단)는 `diagnose`로 흡수하고,
> 둘 다 없던 **소환(recall)** 을 중심에 놓았다. 설계 전환의 근거는 [docs/DECISION_LOG.md](docs/DECISION_LOG.md).

```
ingest(수집) → parse/graph(구조화) → recall(소환) → diagnose(진단) → eval(증빙)
```

## 왜 다른가

| 흔한 접근 | vault-recall |
|---|---|
| 노트를 쌓기만 한다 (무덤) | **질의 → 근거 카드 소환**이 목적. 저장은 수단 |
| LLM이 그럴듯하게 답을 생성 | **생성하지 않는다.** 내 볼트의 근거만 인용하고, 없으면 **공백을 선언** |
| 엣지를 topic 유사도로 근사 | **사람이 승인한 [[위키링크]]가 진짜 엣지** — 그래프 부스트 검색의 신호 |
| "검색 잘 된다" (주장) | **골드셋 Recall@k·MRR로 증빙** (재현 가능한 숫자) |
| 무거운 의존성·서버 | **의존성 0**(표준 라이브러리) · 단일 CLI · 임베딩/LLM은 선택 확장점 |

## 빠른 시작

```bash
pip install -e .            # 의존성 없음 (dev: pip install -e .[dev])

vault-recall scan     demo_vault                       # 파싱·린트·통계 + 노드/엣지 CSV 외부화
vault-recall recall   demo_vault "전환 퍼널 병목" -k 3   # 소환: 근거 카드 + 인용 + 공백
vault-recall diagnose demo_vault                       # orphan·검증률·연결 보강 우선순위
vault-recall eval     demo_vault --gold eval/gold_demo.json   # Recall@k·MRR
vault-recall report   demo_vault -o graph.html         # 인터랙티브 지식그래프 HTML
vault-recall report   demo_vault --query "퍼널 병목"     # 소환 근거를 지도에 불빛으로 하이라이트
vault-recall ingest   demo_vault --urls urls.txt       # URL 목록 → 90_inbox 카드 초안
vault-recall ingest   demo_vault --files ./자료폴더      # md/txt(내장)·pdf/docx(docling) → 카드
vault-recall train    demo_vault                       # 간격반복(SM-2) 오늘의 훈련 카드
vault-recall train    demo_vault --grade "카드명" 4     # 회상 판정 기록 (채점은 사람)
```

동봉된 `demo_vault/`(합성 노트 12개)로 모든 명령이 바로 재현된다. `pytest`(25 tests)도 이 데모 볼트 기준.

## 소환(recall)의 동작 — 핵심 기능

```
$ vault-recall recall <vault> "결제 이탈률이 높게 나왔는데 진짜인지 검증"

# 소환: 결제 이탈률이 높게 나왔는데 진짜인지 검증
## 1. [[답변_충격 지표의 재검증 (이탈률 86%→44%)]] (✓검증 · 20.33)
   - 직접 매칭: 검증, 진짜, 탈률, 이탈, 결제
## 2. [[13일차 — 결제창 이탈률 유저단위 확정·mart 구축]] (✓검증 · 18.85)
## 3. [[MOC_실무]] (✓검증 · 14.08)
   - 연결 근거: 상위 노트의 이웃

## 정직한 공백
볼트가 커버하지 못한 질의 어절 — 다음 학습/기록 후보: ...
```

- **하이브리드 랭킹** = BM25(한국어 음절 bigram) + **그래프 부스트**(위키링크 이웃 확장) + MOC 패널티 + 의미 검색 RRF 융합(가능 시 자동).
- **3단계 신뢰도** = top점수/이상점수 비율로 충분·약함·공백을 구분(스케일 불변). "근거 약함"이면 경고를, "공백"이면 근거 부족 선언을 낸다 — 할루시네이션을 모델이 아니라 **구조**로 차단.
- **HITL 필터** = `--verified-only`로 사람이 검증(`verified: true`)한 지식만 소환.

## 의미 검색 (임베딩) — 자동 활성

`recall`은 임베딩 레이어를 **가능하면 자동으로** 켠다(불가 환경에선 코어만으로 동작, 죽지 않음):

```bash
pip install 'vault-recall[embed]'    # sentence-transformers (리랭커도 이 패키지)

vault-recall recall <vault> "떠난 고객이 다시 돌아오는 비율"            # 임베딩 자동 융합
vault-recall recall <vault> "..." --rerank                          # + cross-encoder 재채점

# 효과 측정 (3단 비교 — 헤더에 활성 레이어 표시)
vault-recall eval <vault> --gold eval/gold_paraphrase.json           # 코어
vault-recall eval <vault> --gold eval/gold_paraphrase.json --embed   # +임베딩
vault-recall eval <vault> --gold eval/gold_paraphrase.json --embed --rerank  # +리랭커
```

- 기본 모델 `intfloat/multilingual-e5-small`(한국어 지원·경량) — `--model`/`VAULT_RECALL_EMBED_MODEL`로 교체(BGE-M3 등). e5 계열의 query:/passage: 프리픽스 자동 처리.
- 임베딩은 `<vault>/.recall_cache/`에 디스크 캐시 — 2회차부터 인코딩 없이 즉시.
- **왜 필요한가(측정된 갭):** 어휘가 겹치지 않는 패러프레이즈 질의에서 코어(BM25)는 R@5 60%에 머문다. 이 갭을 임베딩+리랭커가 닫는다(아래 실측).

### 의미 검색 3단 실측 (career-vault 188노트, 패러프레이즈 10건 — 실기기 재현)

| 구성 | Recall@5 | MRR | 관찰 |
|---|---|---|---|
| 코어 (BM25+그래프) | 60% | 0.600 | 어휘가 겹치는 질의만 잡음 |
| +임베딩 (e5-small, 가중 2.0) | 70% | 0.550 | 의미로 recall↑, 순위 흔들려 MRR 잠깐↓ |
| **+리랭커 (bge-reranker-v2-m3)** | **90%** | **0.800** | **retrieve→rerank로 recall·정밀도 동시↑** |

임베딩이 후보를 넓히고(BM25가 놓친 의미 질의 포착 — 예: "돈 안 들이고 데이터 웨어하우스 운영"→BigQuery 무료한도), 크로스인코더 리랭커가 정답을 다시 위로 정렬한다(임베딩만 쓸 때 4위로 밀렸던 "원인과 결과…"를 1위로 복구). 남은 1건("미래 판매량"→시계열 예측 도구)은 그 노트가 후보 풀에 못 든 candidate-recall 한계로, 후보 확장·노트 요약 보강이 다음 과제. 골드셋 10건 소표본이라 절대값보다 방향으로 읽을 것. 재현: `eval/gold_paraphrase.json`에 `--embed` / `--embed --rerank`.

## 실측 (저자의 실제 지식볼트, 188 노트 · 548 엣지)

| 지표 | 값 |
|---|---|
| 골드셋 25건 Recall@5 | **100%** — 정답 있는 20건 전부 top-5 적중 |
| MRR | **0.873** (20건 중 14건이 1위 적중) |
| 정답이 볼트에 없는 5건 | **5/5 비확신 처리** (강한 공백 3 · 약함 경고 2) — 확신 있는 오답 0 |
| 패러프레이즈 10건(어휘 겹침 없음) | 코어 60% → +임베딩 70% → **+리랭커 90%** (MRR 0.600→0.550→**0.800**) |
| orphan(소환 불가 노트) | 0% (진단→연결 보강 후) |
| 테스트 | 25 passed |

### 기능별 효과크기 (절제 실험, 골드셋 20건)

| 변형 | R@5 | MRR | 효과 |
|---|---|---|---|
| BM25 단어 토큰만 | 90.0% | 0.733 | 기준선 |
| + 한글 음절 bigram | 100% | 0.825 | **+10%p / +0.092 — 최대 효과** |
| + 그래프 부스트 | 100% | 0.825 | 랭킹 효과 0 — **근거 확장용으로만 유지** (소환 결과에 이웃 카드 제공) |
| + MOC 패널티 0.5 | 100% | **0.842** | +0.017 — 허브가 개별 근거를 밀어내는 문제 교정 |

공백 판정도 실측으로 캘리브레이션했다: 절대 점수 임계는 분리 실패(볼트 내 최저 17.7 vs 볼트 밖 최고 17.4)
→ **top점수/이상점수 비율**(스케일 불변)로 교체. in-vault 중앙값 1.23 vs out-vault 중앙값 0.17,
3단계 신뢰도(충분 ≥0.6 / 약함 ≥0.3 / 공백 <0.3)로 "확신 있는 오답"을 구조적으로 없앴다.

## 아키텍처

```
src/vault_recall/
├─ parser.py        # Obsidian 파서: frontmatter·[[위키링크]] (결정적)
├─ graph.py         # 실링크 지식그래프: orphan·허브·컴포넌트 + CSV 외부화
├─ search/
│  ├─ bm25.py       # BM25 + 한국어 음절 bigram 토크나이저 (표준 라이브러리)
│  ├─ hybrid.py     # 그래프 부스트 + RRF 융합
│  └─ embed.py      # 임베딩 provider 확장점 (BGE-M3 등, 선택)
├─ recall.py        # 소환: 근거 인용 + 정직한 공백 + verified 필터
├─ diagnose.py      # 진단: orphan→가까운 MOC 자동 제안(연결 액션), 폴더별 검증률, 중복
├─ evalkit.py       # 골드셋 Recall@k·MRR (공백 기대 질의 지원)
├─ ingest.py        # URL 목록 → inbox 카드 초안 (HITL: verified:false)
└─ report.py        # self-contained HTML 지식그래프 (force-graph)
```

**3층 원칙** — 계산은 수식(결정적 코어), 생성은 선택(provider 확장점), 판정은 사람(verified/승인). 같은 입력이면 언제나 같은 결과가 나온다.

## 참고한 오픈소스 (개념 → 구현 매핑, 10/10 반영)

| 참고 | 가져온 개념 | 이 레포에서 |
|---|---|---|
| [docling](https://github.com/docling-project/docling) | 문서(PDF·docx) 파싱 — 카드 품질은 파싱 품질 | `ingest --files` (md/txt 내장 · pdf/docx는 docling optional provider) |
| [pgvector](https://github.com/pgvector/pgvector) | DB 내 벡터 검색 | 로드맵 3 (볼트 1만 노트 규모에서 저장층 교체) |
| [FlagEmbedding(BGE-M3)](https://github.com/FlagOpen/FlagEmbedding) | 한국어 강한 임베딩+**리랭커** | `embed.py` STProvider(auto·캐시·프리픽스) + `CrossEncoderReranker`(`--rerank`) |
| [react-force-graph](https://github.com/vasturiano/react-force-graph) | 지식지도 + "근거 카드를 불빛으로" | `report.py` HTML + `report --query` 소환 근거 하이라이트 |
| [instructor](https://github.com/567-labs/instructor) | 출력 스키마 강제·검증 | `parser.lint()` — 키 존재 + 값 검증(type 열거·verified 불리언·priority 형식) |
| [ts-fsrs](https://github.com/open-spaced-repetition/ts-fsrs) | 간격반복 훈련(FSRS=SM-2 후계) | `train` 명령 — SM-2 결정적 구현(채점은 사람), FSRS는 provider 교체 경로 |
| [ragflow](https://github.com/infiniflow/ragflow) / [khoj](https://github.com/khoj-ai/khoj) | 내 자료만 근거 + 추적 가능한 인용 | `recall.py`의 인용·3단계 신뢰도·공백 선언 |
| [ragas](https://github.com/explodinggradients/ragas) | RAG 품질의 정량 평가 | `evalkit.py` (결정적 축소판 + 공백 기대 질의) |
| [reor](https://github.com/reorproject/reor) | KG+개인 RAG+휴먼 판정 | 실링크 그래프 + verified 필터 + grade 판정 |

## 루프 완성도

```
수집(ingest: url·files) → 구조화(parse·graph·lint) → 소환(recall: 하이브리드·인용·공백)
   → 진단(diagnose: orphan→연결 제안) → 증빙(eval: R@k·MRR) → 훈련(train: SM-2) → 기록(.recall_cache)
```

## 서재 채우기 — 노션 증분 동기화 (`scripts/sync_notion.py`)

볼트를 "일회성 이관"이 아니라 **살아있는 서재**로 유지하는 조각. 노션 Career-Ops에 새로 추가·수정된 항목만 골라 볼트 카드로 반영한다. 예약 자동화는 클라우드라 로컬 볼트에 못 닿으므로 **사용자 PC에서 직접 실행**하는 독립 스크립트다(외부 의존성 0 — 표준 라이브러리 urllib, Notion 공식 API 2025-09-03 data sources).

```bash
# 1) 노션 통합 토큰 발급(https://www.notion.so/my-integrations) 후 6개 DB를 그 통합과 공유
# 2) 토큰 지정 (Windows: set NOTION_TOKEN=... / mac·linux: export NOTION_TOKEN=...)
export NOTION_TOKEN=ntn_xxxxx
# (최초 1회) 지금 노션에 있는 것 전체를 '이미 반영됨'으로 기준선 설정 — 카드 생성 안 함
python scripts/sync_notion.py --vault "C:/Users/you/career-vault" --baseline
# 이후: 새로 추가·수정된 것만 동기화
python scripts/sync_notion.py --vault "C:/Users/you/career-vault" --dry-run   # 미리보기
python scripts/sync_notion.py --vault "C:/Users/you/career-vault"             # 실제 반영
```

> ⚠ **최초 1회 `--baseline` 필수.** 볼트는 이미 노션에서 한 번 이관돼 있으므로, 이걸 건너뛰면 기존 항목이 전부 "새 카드"로 잡혀 중복 생성된다(`--baseline`은 카드를 만들지 않고 현재 항목을 '반영됨'으로만 표시).

동작 원칙(HITL·중복 방지):
- 새 페이지 → 소속 폴더에 `verified:false` 초안 카드 생성(제목·요약·우선순위·링크·검증상태 자동 매핑).
- 각 카드에 `notion_id`를 남겨 **재실행해도 중복 생성 안 함**(idempotent). 페이지별 `last_edited_time`을 `.recall_cache/`에 저장해 증분 처리.
- 수정된 페이지 → 사람이 큐레이션한 원본은 **건드리지 않고** `90_inbox/_updates/`에 `[UPDATED]` 초안만 남겨 병합하게 함(자동 덮어쓰기 금지).
- 링크(`## 연결`)는 비운 채 생성 → `diagnose`가 orphan으로 잡아 "여기 연결하라"고 안내. 수집은 자동, 편입·검증·연결은 사람.

## 로드맵
1. ~~의미 검색 기본화~~ → **완료** / ~~리랭커~~ → **완료**(`--rerank`, 실측 90%/0.800 — 위 표)
2. ~~훈련 루프~~ → **완료**(SM-2). 다음: FSRS provider·소환 이력 연동(자주 소환된 카드 우선 훈련)
3. 저장층: 볼트 1만 노트 규모에서 pgvector 캐시

## 라이선스 / 데이터
MIT. 레포에는 합성 `demo_vault/`만 포함 — 개인 볼트 데이터는 커밋하지 않는다(실측 수치만 인용).
