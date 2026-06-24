# 1차 소스 맥락 엔진 (v1) 설계 — 브리핑 코리아

> 작성 2026-06-16. Claude + codex 공동 설계. 브레인스토밍 합의 결과.

## 목표 (제품 축 전환)
뉴스 어그리게이터 → **"한 사건에 모든 주체(정부·국회·정당·언론)의 입장/법안/표결/프레이밍을 병치하는 1차 소스 맥락 엔진."**
일반인이 뉴스(2차 가공물)로만 보던 정치를, 정부·국회 **1차 소스**까지 연결해 "전체 그림"으로 보여준다. 포털·뉴스레터·국회사이트 누구도 못 하는 자리.

## v1 범위 (작게, 합법적으로)
- **소스 2개만**: 정책브리핑 `korea.kr`(정부, KOGL 라이선스) + 열린국회 OpenAPI(법안/표결, 이미 사용중).
- **정당·시민행동·수익모델은 v2+로 미룸.**
- 기존 `issues`/`articles`/`members` 구조 **버리지 않고 그 위에 얹음.**

## 핵심 결정 (브레인스토밍 확정)
1. 데이터 모델 = **신규 `source_items` 통합 컬렉션** + 기존 `issues`를 허브로 재사용.
2. 사건 연결 = **자동 후보 생성 + 사람 안전판**(고신뢰는 자동 승인, 애매하면 검수 큐). 순수 자동은 오연결 쓰레기 위험이라 배제(codex).
3. AI(요약·핵심주장·position)는 **수집 시 배치**(GitHub Actions, throttle) — 요청 경로에서 Gemini 안 씀(무료 쿼터 보호).
4. **저작권 안전장치**: 원문 전문 저장 ❌ → 요약 + 짧은 근거문장 + 원문 링크 + 출처표기.

## 아키텍처

### 데이터 모델
```
source_items (신규 컬렉션)
  id            : 안정적 해시(actor+url 기반, 중복제거 키)
  type          : gov_policy | assembly_bill | assembly_vote | news
  actor_type    : government | assembly | party | media
  actor_name    : "기획재정부" / "국민의힘" / "한겨레"
  title         : 원문 제목
  summary       : AI 요약(수집 배치 생성)
  claim_summary : 핵심 주장 1줄
  position      : support|oppose|explain|criticize|propose|neutral|null
  source_bias   : official|left|right|center|foreign|unknown  (utils.source_bias 재사용)
  url           : 원문 링크(필수 — 저작권 안전)
  published_at  : ISO8601
  entities      : { people:[], parties:[], bills:[] }
  bill          : { bill_id, bill_name, proposers[], status } | null
  vote          : { bill_id, result, yes, no, abstain, party_breakdown{} } | null
  issue_id      : 연결된 사건 id | null
  link_status   : auto | pending | confirmed | rejected   (안전판)
  created_at, updated_at

issues (기존 확장)
  + source_counts : { government, assembly, party, media }  (4단 뷰 배지용)
  (기존: status, category, title, summary, timeline[], articles[])
```

### 수집 파이프라인 (services/source_ingest_service.py 신규)
- `ingest_gov_policy()`: korea.kr 정책브리핑 RSS/목록 → `gov_policy` source_item 정규화 → 중복제거(id 해시) → 배치 AI 요약.
- `ingest_assembly()`: 열린국회 법안/표결 API → `assembly_bill`/`assembly_vote` source_item 정규화. (열린국회 키/조인키는 기존 코드 재사용.)
- 공통: dedup(id 존재시 skip/update), entity 추출(법안번호·인물·정당 정규식+키워드), `published_at` 정규화.
- **주기**: `.github/workflows/collect.yml`에 소스별 스텝 추가, cron 단축(예: `*/30 * * * *` 또는 시간별). 뉴스/정부/국회를 분리 수집.

### 사건 연결 (utils/issue_linker.py 신규, 순수 로직 → 테스트 대상)
- `candidate_links(source_item, issues, existing_items)`: 점수 = 엔티티 교집합(인물·정당·법안번호 일치 가중) + 키워드 + 기간 근접.
- 임계값 `>= AUTO`: `link_status=auto`, issue_id 연결(없으면 신규 이슈 시드 생성 후보).
- `LOW <= score < AUTO`: `link_status=pending` → 검수 큐.
- `< LOW`: 미연결.
- 법안번호(`bill_id`) 정확 일치는 강한 신호 → 같은 법안의 gov/bill/vote/news를 한 이슈로 모음.
- **관리자 검수 엔드포인트**: pending 목록 조회 + 승인/거부(`ADMIN_KEY` 보호).

### API (routers/source_router.py 신규 + issue_router 확장)
- `GET /api/issues/{id}` 확장 → `source_panels: { government:[], assembly_bill:[], assembly_vote:[], media:[] }` 포함(4단 뷰).
- `POST /api/sources/ingest` (admin): 수동 수집 트리거(백그라운드).
- `GET /api/sources/pending` (admin): 검수 대기 후보.
- `POST /api/sources/{id}/link` (admin): 승인/거부/이슈 지정.

### 프론트 (이슈 상세 4단 병치)
- `IssueDetail`을 4단 패널로 재구성: 🏛 정부 입장 / 📜 관련 법안 / 🗳 표결 결과 / 📰 언론 프레이밍(기존 관점비교 재사용).
- 각 항목: actor_name·claim_summary·position 배지·원문 링크. 비어있는 패널은 "해당 소스 없음" 빈상태.

## AI 사용 (무료 쿼터 보호)
- 수집 배치에서만 Gemini 호출: `summary`, `claim_summary`, `position` 추출. throttle(`AI_THROTTLE_SEC`) 준수, 실패 시 원문 title 폴백.
- 요청 경로(이슈 조회·뷰)에서는 Gemini 호출 0.

## 범위 밖 (v2+)
정당 소스 수집, 시민행동(의원 연락/청원), 수익모델, 알림/팔로우 루프, 의원 책임성 심화 지표, 완전 자동화(임계값 하향).

## 테스트 전략
- 순수 로직 단위테스트(pytest): `issue_linker`(점수/임계값/법안번호 매칭), source_item 정규화(중복제거 키, entity 추출), source_bias 연동.
- 수집은 외부 API 모킹 또는 샘플 페이로드로 정규화 함수만 테스트.

## 리스크 / 완화
- **오연결(클러스터링 품질)** → 자동+검수 하이브리드, 법안번호 정확매칭 우선, pending 큐.
- **저작권** → 전문 미저장, 요약+링크+출처, KOGL 유형 확인.
- **수집 주기↑ → 비용/쿼터** → AI는 신규 항목만 배치 처리, throttle, dedup으로 중복 호출 차단.
- **korea.kr 구조 변경** → 파서 격리(utils), 실패시 graceful skip + 로그.
