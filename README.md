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

동봉된 `demo_vault/`(합성 노트 12개)로 모든 명령이 바로 재현된다. `pytest`(16 tests)도 이 데모 볼트 기준.

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
pip install 'vault-recall[embed]'    # sentence-transformers
vault-recall recall <vault> "떠난 고객이 다시 돌아오는 비율"   # 자동 융합
vault-recall eval <vault> --gold eval/gold_paraphrase.json --embed   # 효과 측정
```

- 기본 모델 `intfloat/multilingual-e5-small`(한국어 지원·경량) — `--model`/`VAULT_RECALL_EMBED_MODEL`로 교체(BGE-M3 등). e5 계열의 query:/passage: 프리픽스 자동 처리.
- 임베딩은 `<vault>/.recall_cache/`에 디스크 캐시 — 2회차부터 인코딩 없이 즉시.
- **왜 필요한가(측정된 갭):** 어휘가 겹치지 않는 패러프레이즈 질의 10건에서 코어는 R@5 60%에 머문다(정확 어휘 질의는 100%). `eval/gold_paraphrase.json`으로 융합 전후를 직접 비교하라.

## 실측 (저자의 실제 지식볼트, 188 노트 · 548 엣지)

| 지표 | 값 |
|---|---|
| 골드셋 25건 Recall@5 | **100%** — 정답 있는 20건 전부 top-5 적중 |
| MRR | **0.873** (20건 중 14건이 1위 적중) |
| 정답이 볼트에 없는 5건 | **5/5 비확신 처리** (강한 공백 3 · 약함 경고 2) — 확신 있는 오답 0 |
| 패러프레이즈 10건(어휘 겹침 없음) | R@5 60% — **임베딩 레이어가 닫아야 할 갭** (아래) |
| orphan(소환 불가 노트) | 0% (진단→연결 보강 후) |
| 테스트 | 16 passed |

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

## 참고한 오픈소스 (개념 → 구현 매핑)

| 참고 | 가져온 개념 | 이 레포에서 |
|---|---|---|
| [ragflow](https://github.com/infiniflow/ragflow) / [khoj](https://github.com/khoj-ai/khoj) | 내 자료만 근거 + 추적 가능한 인용 | `recall.py`의 인용·공백 선언 |
| [ragas](https://github.com/explodinggradients/ragas) | RAG 품질의 정량 평가 | `evalkit.py` (결정적 축소판) |
| [reor](https://github.com/reorproject/reor) | KG+개인 RAG+휴먼 판정 | 그래프 부스트 + verified 필터 |
| [instructor](https://github.com/567-labs/instructor) | 출력 스키마 강제 | `parser.lint()` 카드 스키마 검증 |
| [FlagEmbedding(BGE-M3)](https://github.com/FlagOpen/FlagEmbedding) | 한국어 강한 임베딩·리랭크 | `embed.py` provider (auto·캐시·프리픽스) |
| [react-force-graph](https://github.com/vasturiano/react-force-graph) | 인터랙티브 지식지도 | `report.py` HTML 리포트 |
| [pgvector](https://github.com/pgvector/pgvector) | DB 내 벡터 검색 | 로드맵(볼트가 커지면 저장층 교체) |
| [ts-fsrs](https://github.com/open-spaced-repetition/ts-fsrs) | 간격반복 훈련 | 로드맵(소환 다음 단계 = 훈련) |

## 로드맵
1. ~~의미 검색 기본화~~ → **완료** (auto 활성·캐시·e5/BGE 지원). 다음: 리랭커(BGE reranker)
2. 훈련 루프: 소환 이력 기반 간격반복(FSRS) — "소환되게 저장"에서 "기억되게 훈련"으로
3. 저장층: 볼트 1만 노트 규모에서 pgvector 캐시

## 라이선스 / 데이터
MIT. 레포에는 합성 `demo_vault/`만 포함 — 개인 볼트 데이터는 커밋하지 않는다(실측 수치만 인용).
