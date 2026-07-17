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
vault-recall ingest   demo_vault --urls urls.txt       # URL 목록 → 90_inbox 카드 초안
```

동봉된 `demo_vault/`(합성 노트 12개)로 모든 명령이 바로 재현된다. `pytest`(11 tests)도 이 데모 볼트 기준.

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

- **하이브리드 랭킹** = BM25(한국어 음절 bigram 토크나이저) + **그래프 부스트**(상위 근거의 위키링크 이웃을 감쇠 점수로 확장) + 선택적 임베딩 RRF 융합.
- **정직한 공백** = 근거 점수가 임계 미만이면 "근거 부족"을 선언하고, 커버되지 않은 질의 어절을 그대로 보여준다. 할루시네이션을 모델이 아니라 **구조**로 차단한다.
- **HITL 필터** = `--verified-only`로 사람이 검증(`verified: true`)한 지식만 소환.

## 실측 (저자의 실제 지식볼트, 188 노트 · 548 엣지)

| 지표 | 값 |
|---|---|
| 골드셋 12건 Recall@5 | **91.7%** |
| MRR | **0.808** (12건 중 8건이 1위 적중) |
| 데모 볼트 골드셋 5건 | Recall@5 100% · MRR 1.000 |
| orphan(소환 불가 노트) | 0% (진단→연결 보강 후) |
| 테스트 | 11 passed (파서·BM25·그래프 부스트·공백 선언·평가·수집) |

실패 1건도 기록해 둔다: "간격반복 알고리즘" 질의는 볼트에 정답이 없어 **공백 선언이 기대**였으나, '복습'을 다루는 인접 노트가 임계(2.0)를 넘겨 근거로 제시됐다. 공백 임계는 휴리스틱이며 near-miss 주제에서 경계가 흐려진다 — 알려진 한계로 명시한다.

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

## 참고한 오픈소스 (개념 → 구현 매핑)

| 참고 | 가져온 개념 | 이 레포에서 |
|---|---|---|
| [ragflow](https://github.com/infiniflow/ragflow) / [khoj](https://github.com/khoj-ai/khoj) | 내 자료만 근거 + 추적 가능한 인용 | `recall.py`의 인용·공백 선언 |
| [ragas](https://github.com/explodinggradients/ragas) | RAG 품질의 정량 평가 | `evalkit.py` (결정적 축소판) |
| [reor](https://github.com/reorproject/reor) | KG+개인 RAG+휴먼 판정 | 그래프 부스트 + verified 필터 |
| [instructor](https://github.com/567-labs/instructor) | 출력 스키마 강제 | `parser.lint()` 카드 스키마 검증 |
| [FlagEmbedding(BGE-M3)](https://github.com/FlagOpen/FlagEmbedding) | 한국어 강한 임베딩·리랭크 | `embed.py` provider (선택) |
| [react-force-graph](https://github.com/vasturiano/react-force-graph) | 인터랙티브 지식지도 | `report.py` HTML 리포트 |
| [pgvector](https://github.com/pgvector/pgvector) | DB 내 벡터 검색 | 로드맵(볼트가 커지면 저장층 교체) |
| [ts-fsrs](https://github.com/open-spaced-repetition/ts-fsrs) | 간격반복 훈련 | 로드맵(소환 다음 단계 = 훈련) |

## 로드맵
1. `recall --embed` 기본화(BGE-M3) + 리랭커 — 의미 검색 정밀도
2. 훈련 루프: 소환 이력 기반 간격반복(FSRS) — "소환되게 저장"에서 "기억되게 훈련"으로
3. 저장층: 볼트 1만 노트 규모에서 pgvector 캐시

## 라이선스 / 데이터
MIT. 레포에는 합성 `demo_vault/`만 포함 — 개인 볼트 데이터는 커밋하지 않는다(실측 수치만 인용).
