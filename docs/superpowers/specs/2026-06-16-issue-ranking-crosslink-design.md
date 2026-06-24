# 이슈 사건성 랭킹 + 법안 교차연결 (v1) 설계 — 브리핑 코리아

> 2026-06-16. Claude + codex 공동 설계. 라이브 리뷰 후속.

## 문제
1차 소스 맥락 엔진은 섰지만 **"많이 수집했는데 중요해 보이지 않음"**. 구체적으로:
- 자동 이슈가 **절차적 대안법안(국토위원장 대안)으로 도배** → 흥미로운 수동 이슈를 밀어냄. 랭킹 없음.
- 4단 패널이 비어 차별점이 안 보임 — gov(의안번호)·news(법률명)와 국회(PRC_id)의 **식별자 불일치**로 교차연결 실패.

## 목표
**선별·연결·랭킹**으로 "중요한 것이 중요해 보이게". 기능 추가 아님.

## 핵심 결정 (codex 반영)
1. **식별자 먼저, 랭킹 다음.** 법률명 정규화 + 의안번호로 교차연결을 먼저 살린 뒤 점수화.
2. **법률명은 canonical 키가 아니라 '후보' 신호.** 상법/방송법 등 과합침 방지 위해 최종 연결은 의안번호 일치 또는 (법률명 + 소관위 + 날짜근접) 조합.
3. **절차성 감점이 최우선 즉효.** 대안/위원장 절차안을 감점해 도배 해소.
4. 임베딩·완전 identity 테이블·parent-child는 v2.

## 아키텍처 (기존 위에 얹기)

### 순수 로직 (테스트 대상)
**`utils/law_name.py`**
- `normalize_law_name(title)`: 절차어 제거(`일부개정법률안`,`전부개정`,`제정`,`대안`,`(위원장)`,`(의장)`, 괄호, 공백) → 법률명. 예 `항공안전법 일부개정법률안(대안)(국토교통위원장)` → `항공안전법`.
- `is_procedural(title)`: `대안`/`위원장`/`의장 제출` 포함 여부.

**`utils/newsworthiness.py`**
- `vote_contention(vote)`: party_breakdown으로 갈등도 0~1 (교차당 반대 있음/찬반 접전이면 높음, 만장일치면 0).
- `issue_score(issue, source_items, article_count)`:
  `score = contention*4 + min(source_types,4)*1.5 + min(news,5)*1.2 + gov_connected*2 − procedural_penalty`
  - `procedural_penalty = 5` if 모든 연결 법안이 procedural and no news and contention==0.
- 임계값: `PROMOTE = 3.0`(이슈 노출 최소), 패널 2개 미만이면 비노출.

### 데이터 (필드 추가, 새 컬렉션 없음)
- `source_items`에 `law_name`(정규화), `procedural`(bool) 추가(정규화 시).
- `issues`(자동)에 `law_name`, `newsworthiness`(점수), `procedural`(bool) 추가.

### 교차연결 (services/source_link_service 확장)
- 법안 source의 `law_name` + `의안번호(BILL_NO)`를 이슈 entities에 반영.
- gov/news → 이슈 연결: 의안번호 직접 일치 1순위; 없으면 `law_name`이 gov/news 제목·요약에 등장 + 날짜창(표결일 −14~+7) + (가능 시 소관위/키워드 1개 더) → 연결. 약한 매칭은 pending.
- 뉴스는 `articles`를 law_name으로 스캔해 이슈 `article_ids`에 추가(4단 media 패널).

### 랭킹/필터 (issue_service + 프론트)
- `list_summaries`에 `sort=newsworthiness` 옵션 + 자동이슈 노출조건(score≥PROMOTE AND panels≥2).
- 자동 클러스터 생성 시: 점수/패널 미달이면 이슈 생성 보류(source_item로만 유지).
- 프론트 이슈목록/홈: 점수순 정렬, 절차안 하위.

## 구현 순서 (codex)
1. 법률명/절차 추출기(순수)  2. 사건성 점수(순수)  3. 정규화를 수집/클러스터에 반영(law_name·procedural 저장)  4. **절차성 감점 먼저** 적용해 클러스터 생성/노출 게이트  5. 법률명+의안번호 교차연결(gov/news)  6. 점수순 랭킹 API + 프론트

## 범위 밖 (v2+)
임베딩 유사도 매칭, 독립 `bill_identity` 테이블, 대안↔원안 parent-child, 정당 소스, 알림.

## 테스트
순수 로직 pytest: `normalize_law_name`(절차어 제거 케이스), `is_procedural`, `vote_contention`(만장일치 0/접전 높음), `issue_score`(절차안 감점/뉴스가점). 교차연결은 샘플로 law_name 매칭 검증.

## 리스크/완화
- **법률명 과합침** → 의안번호 우선 + 소관위/날짜 보조, 약매칭 pending.
- **절차성 감점 과함**(중요한 대안법안도 감점) → 뉴스 연결/갈등도 있으면 감점 상쇄.
- **무료 쿼터** → 점수/정규화는 규칙 기반(AI 0). 사건 요약 AI는 승격 이슈에만(차기).
