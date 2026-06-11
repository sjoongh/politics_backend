# 이슈 관점 비교 (편향/다출처) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use `- [ ]`.

**Goal:** 이슈에 묶인 다출처 기사를 매체 성향(진보/중도/보수/공식)별로 그룹화해 "이 사건을 어느 진영이 어떻게 보도했는지" + Blindspot(한쪽만 보도)을 보여준다.

**Architecture:** 매체→성향 매핑은 firebase 비의존 순수 모듈 `utils/source_bias.py`(pytest). 백엔드 이슈 상세 API에 `perspectives`(성향별 그룹 + 집계 + blindspot) 추가. 프론트 이슈 상세 모달에 "관점 비교" 섹션. 군집화는 기존 이슈 구조 재활용(자동군집은 후속).

**Tech Stack:** FastAPI(원본 백엔드), React. 검증: pytest(순수 매핑) + 실 Firestore(임시 이슈) + 프론트 빌드.

**참고(법적 안전):** 매체 성향 라벨은 *통용되는 분류*를 출발점으로 하며 설정 가능. AI 편향 "판정" 없음. 출처·원문 링크 유지. 화면에 "성향 분류는 참고용" 고지.

---

## 두 레포
- 백엔드 `/Users/manager/side/politics_backend` (Task 1,2). 작업 전 `git checkout -b feat/issue-perspectives`. `.venv` 존재.
- 프론트 `/Users/manager/side/politics_front` (Task 3). 작업 전 `git checkout -b feat/issue-perspectives`.

## 기존 코드(참고)
- `services/issue_service.py` `get_detail`: 이슈 + `events`(정렬) + `articles`(article_public 형태: id,title,ai_summary,source,source_url,image_url,category,published_at) + disclaimer 반환. 여기에 `perspectives` 추가.
- 저장된 `source` 값 예: 연합뉴스, 한국경제, 세계일보, 한겨레, 동아일보, 서울경제, 대통령실, 정책 뉴스, 부처별 브리핑.
- 프론트 `src/components/IssueDetail.jsx`: official_links/타임라인/관련뉴스 렌더. 여기에 "관점 비교" 추가.

---

## Task 0: 크롤링 매체 확장 (외신 비중↑) (백엔드)

**Files:** Modify `services/news_service.py` (`self.rss_feeds["정치"]` + `_clean_source` domain_map)
**라이브 검증된 추가 피드:** BBC코리아(35), 경향신문 정치(50), SBS 정치(29), 오마이뉴스(20). (한겨레 기존 URL은 현재 0건이지만 per-feed try/except로 무해, 유지)

- [ ] **Step 1:** `self.rss_feeds`의 `"정치"` 리스트에 4개 추가 (기존 항목 유지, 리스트 끝에):
```python
                "https://feeds.bbci.co.uk/korean/rss.xml",  # BBC 코리아 (외신)
                "http://www.khan.co.kr/rss/rssdata/politic_news.xml",  # 경향신문 정치
                "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01",  # SBS 정치
                "http://rss.ohmynews.com/rss/politics.xml",  # 오마이뉴스 정치
```

- [ ] **Step 2:** `_clean_source`의 `domain_map`에 매핑 추가:
```python
            "bbc.co.uk": "BBC 코리아", "bbci.co.uk": "BBC 코리아",
            "khan.co.kr": "경향신문", "sbs.co.kr": "SBS", "ohmynews.com": "오마이뉴스",
```

- [ ] **Step 3:** 문법 + 피드 파싱 라이브 확인 — `python3 -m py_compile services/news_service.py && echo ok`. 그리고 새 피드 4개가 `feedparser`로 entries>0인지 위에서 이미 검증함.

- [ ] **Step 4: Commit**
```bash
git add services/news_service.py
git commit -m "feat(crawl): add BBC Korea (foreign) + 경향/SBS/오마이뉴스 RSS feeds"
```

---

## Task 1: 매체 성향 순수 로직 + 테스트 (백엔드)

**Files:** Create `utils/source_bias.py`, `tests/test_source_bias.py`

- [ ] **Step 1: 실패 테스트 `tests/test_source_bias.py`**
```python
from utils.source_bias import source_leaning, bias_breakdown


def test_source_leaning_known():
    assert source_leaning("한겨레") == "left"
    assert source_leaning("동아일보") == "right"
    assert source_leaning("연합뉴스") == "center"
    assert source_leaning("BBC 코리아") == "foreign"
    assert source_leaning("대통령실") == "official"
    assert source_leaning("듣보잡신문") == "unknown"
    assert source_leaning(None) == "unknown"


def test_source_leaning_partial_match():
    # 저장된 source가 "한겨레신문" 처럼 변형돼도 매칭
    assert source_leaning("한겨레신문") == "left"


def test_bias_breakdown_counts_and_blindspot():
    arts = [{"source": "한겨레"}, {"source": "경향신문"}, {"source": "연합뉴스"}]
    out = bias_breakdown(arts)
    assert out["counts"]["left"] == 2
    assert out["counts"]["center"] == 1
    assert out["counts"]["right"] == 0
    assert out["total"] == 3
    assert out["blindspot"] == "right"  # 보수 매체 미보도


def test_bias_breakdown_no_blindspot_when_both_sides():
    arts = [{"source": "한겨레"}, {"source": "동아일보"}]
    out = bias_breakdown(arts)
    assert out["blindspot"] is None


def test_bias_breakdown_empty():
    out = bias_breakdown([])
    assert out["total"] == 0 and out["blindspot"] is None
```

- [ ] **Step 2: 실패 확인** — `source .venv/bin/activate && python -m pytest tests/test_source_bias.py -v` → FAIL.

- [ ] **Step 3: `utils/source_bias.py` 구현** (firebase 비의존)
```python
"""매체 성향 매핑 순수 로직 (firebase 비의존, 테스트 대상).
라벨은 통용되는 분류를 출발점으로 한 참고값이며 설정 가능."""

# 성향: left(진보) / right(보수) / center(중도·통신사) / official(공식)
_LEANING = {
    "left": ["한겨레", "경향", "오마이뉴스", "프레시안", "민중"],
    "right": ["동아", "조선", "중앙", "문화일보", "세계일보", "한국경제", "서울경제", "매일경제"],
    "center": ["연합뉴스", "연합뉴스TV", "뉴시스", "뉴스1", "YTN", "SBS", "KBS", "MBC"],
    "foreign": ["BBC", "VOA", "NHK", "CNN", "로이터", "AFP", "외신"],
    "official": ["대통령실", "정책", "부처", "정부", "브리핑", "청와대"],
}


def source_leaning(source) -> str:
    """매체명으로 성향 반환. 부분 일치 허용. 미상은 'unknown'."""
    if not source:
        return "unknown"
    for leaning, names in _LEANING.items():
        if any(name in source for name in names):
            return leaning
    return "unknown"


def bias_breakdown(articles) -> dict:
    """기사 목록의 성향별 집계 + blindspot(정치 진영 한쪽만 보도) 계산."""
    counts = {"left": 0, "center": 0, "right": 0, "foreign": 0, "official": 0, "unknown": 0}
    for a in (articles or []):
        counts[source_leaning(a.get("source", ""))] += 1
    total = sum(counts.values())
    blindspot = None
    if counts["left"] > 0 and counts["right"] == 0:
        blindspot = "right"
    elif counts["right"] > 0 and counts["left"] == 0:
        blindspot = "left"
    return {"counts": counts, "total": total, "blindspot": blindspot}
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_source_bias.py -v` → 5 passed.

- [ ] **Step 5: Commit**
```bash
git add utils/source_bias.py tests/test_source_bias.py
git commit -m "feat(perspectives): source leaning map + bias_breakdown (pure logic) + tests"
```

---

## Task 2: 이슈 상세에 perspectives 추가 (백엔드)

**Files:** Modify `services/issue_service.py`

- [ ] **Step 1: import 추가** — 상단 import에:
```python
from utils.source_bias import source_leaning, bias_breakdown
```

- [ ] **Step 2: `get_detail`에서 articles 계산 직후 perspectives 추가** — `issue["articles"] = articles` 다음 줄에 추가:
```python
            groups = {"left": [], "center": [], "right": [], "foreign": [], "official": [], "unknown": []}
            for a in articles:
                groups[source_leaning(a.get("source", ""))].append({
                    "title": a.get("title"),
                    "source": a.get("source"),
                    "source_url": a.get("source_url"),
                })
            issue["perspectives"] = {
                "breakdown": bias_breakdown(articles),
                "groups": groups,
                "disclaimer": "매체 성향 분류는 통용되는 기준을 참고한 값이며 절대적이지 않습니다.",
            }
```

- [ ] **Step 3: 문법 + 임포트 검증** — `python3 -m py_compile services/issue_service.py && echo ok` 그리고 `python3 -c "import services.issue_service" 2>&1 | tail -1` (Firebase env .env로 로드, import 성공이면 OK).

- [ ] **Step 4: 실 Firestore 왕복 검증** — 임시 이슈에 2개 성향 기사 연결 후 perspectives 확인:
```bash
source .venv/bin/activate && python3 - <<'PY'
import asyncio
from firebase.firebase_config import db
from models.model import IssueSeed
from services.issue_service import issue_service

async def m():
    r = await issue_service.create(IssueSeed(title="[TEMP] 관점테스트", category="정치"))
    iid = r["data"]["id"]
    # 가짜 기사 2건(서로 다른 성향) 생성
    db.collection("articles").document("tmpL").set({"id":"tmpL","title":"진보보도","source":"한겨레","source_url":"http://x/l","ai_summary":"","category":"정치","published_at":"2026-06-11","image_url":""})
    db.collection("articles").document("tmpR").set({"id":"tmpR","title":"보수보도","source":"동아일보","source_url":"http://x/r","ai_summary":"","category":"정치","published_at":"2026-06-11","image_url":""})
    await issue_service.add_articles(iid, ["tmpL","tmpR"])
    d = (await issue_service.get_detail(iid))["data"]
    p = d["perspectives"]
    print("counts:", p["breakdown"]["counts"], "blindspot:", p["breakdown"]["blindspot"])
    print("left titles:", [g["title"] for g in p["groups"]["left"]], "right:", [g["title"] for g in p["groups"]["right"]])
    # 정리
    db.collection("issues").document(iid).delete()
    db.collection("articles").document("tmpL").delete()
    db.collection("articles").document("tmpR").delete()
    print("cleaned")
asyncio.run(m())
PY
```
Expected: counts left=1 right=1, blindspot None, left=['진보보도'] right=['보수보도'], cleaned.

- [ ] **Step 5: Commit**
```bash
git add services/issue_service.py
git commit -m "feat(perspectives): issue detail returns source-leaning grouped perspectives + blindspot"
```

---

## Task 3: 프론트 — 이슈 상세 "관점 비교" 섹션 (프론트 레포)

**Files:** Modify `src/components/IssueDetail.jsx`, `src/theme/tokens.css`

- [ ] **Step 1: `IssueDetail.jsx`에 관점 비교 섹션 추가** — `detail.summary` 렌더 다음(official_links 앞)에 삽입:
```jsx
            {detail.perspectives && detail.perspectives.breakdown.total > 0 && (
              <div className="perspectives">
                <div className="issue-section-title">📊 관점 비교</div>
                <div className="persp-bar">
                  {['left', 'center', 'right', 'foreign'].map((k) => {
                    const n = detail.perspectives.breakdown.counts[k] || 0;
                    const total = detail.perspectives.breakdown.total || 1;
                    const pct = Math.round((n / total) * 100);
                    return n > 0 ? (
                      <div key={k} className={`persp-seg persp-seg--${k}`} style={{ width: `${pct}%` }} title={`${pct}%`}>
                        {pct}%
                      </div>
                    ) : null;
                  })}
                </div>
                <div className="persp-legend">
                  <span><i className="persp-dot persp-seg--left" /> 진보 {detail.perspectives.breakdown.counts.left}</span>
                  <span><i className="persp-dot persp-seg--center" /> 중도 {detail.perspectives.breakdown.counts.center}</span>
                  <span><i className="persp-dot persp-seg--right" /> 보수 {detail.perspectives.breakdown.counts.right}</span>
                  <span><i className="persp-dot persp-seg--foreign" /> 외신 {detail.perspectives.breakdown.counts.foreign}</span>
                </div>
                {detail.perspectives.breakdown.blindspot && (
                  <div className="persp-blindspot">
                    ⚠️ {detail.perspectives.breakdown.blindspot === 'left' ? '진보' : '보수'} 성향 매체는 이 사건을 보도하지 않았습니다.
                  </div>
                )}
                {['left', 'center', 'right', 'foreign'].map((k) => {
                  const items = detail.perspectives.groups[k] || [];
                  return items.length > 0 ? (
                    <div key={k} className="persp-group">
                      <div className={`persp-group__label persp-seg--${k}`}>
                        {({ left: '진보', center: '중도', right: '보수', foreign: '외신' })[k]}
                      </div>
                      {items.map((it, i) => (
                        <a key={i} href={it.source_url} target="_blank" rel="noreferrer" className="persp-item">
                          <span className="persp-item__src">{it.source}</span> {it.title}
                        </a>
                      ))}
                    </div>
                  ) : null;
                })}
                <p className="persp-disclaimer">{detail.perspectives.disclaimer}</p>
              </div>
            )}
```

- [ ] **Step 2: `src/theme/tokens.css` 끝에 추가**
```css

/* ===== 관점 비교 ===== */
.perspectives { margin: 16px 0; }
.persp-bar { display: flex; height: 22px; border-radius: var(--radius-pill); overflow: hidden; background: var(--badge-bg); }
.persp-seg { font-size: 11px; color: #fff; text-align: center; line-height: 22px; min-width: 28px; }
.persp-seg--left { background: #2563eb; }
.persp-seg--center { background: #6b7280; }
.persp-seg--right { background: #dc2626; }
.persp-seg--foreign { background: #7c3aed; }
.persp-legend { display: flex; gap: 14px; margin: 8px 0; font-size: 12px; color: var(--text-secondary); }
.persp-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 4px; }
.persp-blindspot { font-size: 12.5px; color: var(--text); background: var(--badge-bg); padding: 8px 10px; border-radius: var(--radius-md); margin: 8px 0; }
.persp-group { margin: 10px 0; }
.persp-group__label { display: inline-block; color: #fff; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: var(--radius-pill); margin-bottom: 6px; }
.persp-item { display: block; font-size: 13px; color: var(--text); text-decoration: none; padding: 3px 0; }
.persp-item__src { color: var(--text-secondary); font-size: 11.5px; }
.persp-disclaimer { font-size: 11px; color: var(--text-secondary); margin-top: 10px; }
```

- [ ] **Step 3: 빌드** — `cd /Users/manager/side/politics_front && CI=false npm run build 2>&1 | grep -E "Compiled|Failed"` → Compiled successfully.

- [ ] **Step 4: Commit**
```bash
git add src/components/IssueDetail.jsx src/theme/tokens.css
git commit -m "feat(perspectives): issue detail 관점 비교 section (bias bar + grouped headlines + blindspot)"
```

---

## Self-Review
- 스펙 커버리지: 매체 성향 매핑(T1)·이슈 perspectives API(T2)·프론트 비교 UI(T3). 성향분류·집계·blindspot·그룹·고지 모두 포함.
- 순수 로직(source_bias)은 pytest로 실제 검증, API는 실 Firestore 왕복, 프론트는 빌드.
- 타입 일관성: `source_leaning`/`bias_breakdown` → get_detail `perspectives.{breakdown:{counts,total,blindspot}, groups, disclaimer}` → 프론트 동일 키 소비.
- 법적: 성향 라벨 참고용 고지, AI 판정 없음.

## 다음 (3·4·5)
3️⃣ 카카오 소셜 로그인 → 4️⃣ 의원 표결·공약 → 5️⃣ 푸시 다이제스트. 각 별도 brainstorming→plan.
