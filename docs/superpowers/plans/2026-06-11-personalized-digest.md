# 개인화 다이제스트 (인앱) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use `- [ ]`.

**Goal:** 사용자의 관심 키워드로 기사를 필터한 "맞춤 다이제스트"(오늘의 요약 + 관심 매칭 기사)를 인앱으로 제공한다. (실제 FCM 푸시 발송은 배포 후 별도)

**Architecture:** 관심 매칭 로직은 firebase 비의존 순수 모듈 `utils/digest.py`(pytest). 백엔드 `GET /api/news/digest`가 관심 키워드로 최근 기사 필터. 프론트는 "맞춤" 탭(다이제스트) + 마이페이지 관심 키워드 편집(토큰 인증으로 profile 업데이트).

**Tech Stack:** FastAPI(원본), React. 검증: pytest(매칭) + 실 Firestore(digest) + 프론트 빌드.

**전제:** 토큰 연동 완료됨(로그인 시 user.interests 반환·저장). `update_user_profile`이 interests 업데이트 처리.

작업 전 백엔드 `git checkout -b feat/digest`, 프론트 동일.

---

## Task 1: 관심 매칭 순수 로직 + digest 서비스 (백엔드)

**Files:** Create `utils/digest.py`, `tests/test_digest.py`. Modify `services/news_service.py`.

- [ ] **Step 1: 실패 테스트 `tests/test_digest.py`**
```python
from utils.digest import matches_interests


def test_match_in_title():
    a = {"title": "대통령 거부권 행사", "keywords": []}
    assert matches_interests(a, ["거부권"]) is True


def test_match_in_keywords():
    a = {"title": "본회의 통과", "keywords": ["예산", "추경"]}
    assert matches_interests(a, ["추경"]) is True


def test_no_match():
    a = {"title": "날씨 맑음", "keywords": ["기상"]}
    assert matches_interests(a, ["국회"]) is False


def test_empty_interests_false():
    assert matches_interests({"title": "x", "keywords": []}, []) is False
    assert matches_interests({"title": "x"}, ["  "]) is False


def test_case_insensitive():
    assert matches_interests({"title": "AI 정책", "keywords": []}, ["ai"]) is True
```

- [ ] **Step 2: 실패 확인** — `source .venv/bin/activate && python -m pytest tests/test_digest.py -v` → FAIL.

- [ ] **Step 3: `utils/digest.py`**
```python
"""개인화 관심 매칭 순수 로직 (firebase 비의존, 테스트 대상)."""


def matches_interests(article, interests) -> bool:
    """기사 제목/키워드에 관심 키워드가 하나라도 포함되면 True."""
    terms = [i.strip().lower() for i in (interests or []) if i and i.strip()]
    if not terms:
        return False
    hay = (article.get("title", "") + " " + " ".join(article.get("keywords") or [])).lower()
    return any(t in hay for t in terms)
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_digest.py -v` → 5 passed.

- [ ] **Step 5: `news_service.py`에 import + get_digest 추가** — 상단 import에 `from utils.digest import matches_interests` 추가. `get_article_by_id` 메서드 다음(클래스 안)에 추가:
```python
    async def get_digest(self, interests, limit: int = 30) -> Dict[str, Any]:
        """관심 키워드로 최근 기사 필터."""
        try:
            if not interests:
                return {"success": True, "message": "관심사가 없습니다.", "data": {"articles": [], "count": 0}}
            query = (db.collection("articles")
                     .order_by("published_at", direction=firestore.Query.DESCENDING)
                     .limit(100))
            matched = []
            for doc in query.stream():
                a = doc.to_dict()
                if matches_interests(a, interests):
                    matched.append(a)
                if len(matched) >= limit:
                    break
            return {"success": True, "message": "맞춤 조회 성공", "data": {"articles": matched, "count": len(matched)}}
        except Exception as e:
            return {"success": False, "message": f"맞춤 조회 오류: {str(e)}"}
```
(`firestore`는 news_service 상단에서 이미 import됨: `from google.cloud import firestore`.)

- [ ] **Step 6: 문법 + 라이브 검증** — Run:
```bash
source .venv/bin/activate && python3 -m py_compile services/news_service.py && python3 - <<'PY' 2>&1 | grep -vE "UserWarning|return query|Firebase 초기화|FutureWarning|google|^$|updates|README|https://git"
import asyncio
from services.news_service import news_service
async def m():
    r = await news_service.get_digest(["대통령", "국회"], limit=5)
    print("digest:", r["success"], "count:", r["data"]["count"])
    for a in r["data"]["articles"][:2]:
        print(" -", a.get("title","")[:40])
asyncio.run(m())
PY
```
Expected: `digest: True count: N` (N>=0; 실 기사 매칭 시 제목 출력).

- [ ] **Step 7: Commit**
```bash
git add utils/digest.py tests/test_digest.py services/news_service.py
git commit -m "feat(digest): interest matching (pure) + news_service.get_digest"
```

---

## Task 2: digest 라우터 (백엔드)

**Files:** Modify `routers/news_router.py`

- [ ] **Step 1: `/digest` 엔드포인트 추가** — ⚠️ 반드시 `@router.get("/{article_id}")` **앞에** 추가(안 그러면 digest가 article_id로 잡힘). `@router.post("/collect")` 블록과 `@router.get("/{article_id}")` 사이에 삽입:
```python
@router.get("/digest", response_model=ResponseModel)
async def get_digest(interests: str = "", limit: int = 30):
    """관심 키워드(쉼표구분)로 맞춤 기사 조회."""
    items = [i for i in interests.split(",") if i.strip()]
    return await news_service.get_digest(items, limit)
```

- [ ] **Step 2: 문법 검증** — `python3 -m py_compile routers/news_router.py && echo ok`. `grep -n "digest" routers/news_router.py`.

- [ ] **Step 3: 라이브 검증(라우트 순서)** — 서버 없이 라우트 순서만 확인: `grep -n "router.get" routers/news_router.py` → `/digest`가 `/{article_id}` 보다 위인지 확인.

- [ ] **Step 4: Commit**
```bash
git add routers/news_router.py
git commit -m "feat(digest): GET /api/news/digest endpoint (before /{article_id})"
```

---

## Task 3: 프론트 "맞춤" 탭 (다이제스트)

**Files (politics_front):** Create `src/hooks/digest.js`, `src/components/useDigest.jsx`. Modify `src/App.jsx`, `src/components/layout/Navigation.jsx`.

- [ ] **Step 1: `src/hooks/digest.js`**
```js
import api from './api';

export async function getDigest(interests = []) {
  const params = { interests: interests.join(','), limit: 30 };
  const res = await api.get('/api/news/digest', { params });
  return res.data.data?.articles || [];
}
```

- [ ] **Step 2: `src/components/useDigest.jsx`**
```jsx
import { useState, useEffect } from 'react';
import { getDigest } from '../hooks/digest';

export function useDigest(interests) {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const list = interests || [];
    if (list.length === 0) { setArticles([]); return; }
    let active = true;
    setLoading(true);
    getDigest(list)
      .then((a) => { if (active) setArticles(a); })
      .catch(() => { if (active) setArticles([]); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [JSON.stringify(interests)]);

  return { articles, loading };
}
```

- [ ] **Step 3: `App.jsx` — import + 훅 + 탭 + case**
import 추가(다른 import 묶음에):
```jsx
import { useDigest } from './components/useDigest';
```
`const dailySummary = useDailySummary();` 다음 줄에:
```jsx
  const { articles: digestArticles, loading: digestLoading } = useDigest(user?.interests);
```
`tabs` 배열에서 user가 있을 때만 보이도록 — `{ id: 'issues', ... }` 다음에:
```jsx
    ...(user ? [{ id: 'digest', label: '맞춤', icon: '✨' }] : []),
```
`renderTabContent`의 `case 'members':` 앞(또는 적절한 위치)에 추가:
```jsx
      case 'digest':
        return (
          <div>
            <div className="section-title">✨ 맞춤 다이제스트</div>
            <DailySummaryCard summary={dailySummary} />
            {!user?.interests || user.interests.length === 0 ? (
              <EmptyState message="마이페이지에서 관심 키워드를 등록하면 맞춤 뉴스를 보여드려요." icon="✨" />
            ) : digestLoading ? (
              <div className="feed-grid">{[1, 2, 3].map((n) => <SkeletonCard key={n} />)}</div>
            ) : digestArticles.length > 0 ? (
              <div className="feed-grid">
                {digestArticles.map((news, idx) => (
                  <NewsCard key={news.id || idx} item={news} type="news" onDetailClick={handleDetailClick} />
                ))}
              </div>
            ) : (
              <EmptyState message="관심 키워드에 맞는 최신 기사가 아직 없어요." icon="✨" />
            )}
          </div>
        );
```

- [ ] **Step 4: `Navigation.jsx` — 아이콘** — lucide import에 `Sparkles` 추가, ICONS에 `digest: Sparkles,` 추가(mypage 앞).

- [ ] **Step 5: 빌드** — `cd /Users/manager/side/politics_front && CI=false npm run build 2>&1 | grep -E "Compiled|Failed"` → Compiled successfully.

- [ ] **Step 6: Commit**
```bash
git add src/hooks/digest.js src/components/useDigest.jsx src/App.jsx src/components/layout/Navigation.jsx
git commit -m "feat(digest): 맞춤 tab (interest-based digest + daily summary)"
```

---

## Task 4: 마이페이지 관심 키워드 편집 (프론트)

**Files:** Modify `src/components/MyPage.jsx`, `src/hooks/useMyPage.js` (관심사 저장 함수 확인/추가).

- [ ] **Step 1: `useMyPage.js` 확인** — `updateInterests(interests)` 가 없으면 추가:
```js
  const updateInterests = async (interests) => {
    const res = await api.put('/api/auth/profile', { interests });
    return res.data;
  };
```
그리고 return에 `updateInterests` 포함. (이미 있으면 생략. `api` import 확인.)

- [ ] **Step 2: `MyPage.jsx` — 관심 키워드 편집 UI** — `useMyPage`에서 `updateInterests`도 받고, `useAppContext`의 `user`,`setUser` 사용. 프로필 블록(`<Divider sx={{ my: 2 }} />`) 다음에 추가:
```jsx
        <div style={{ marginBottom: 16 }}>
          <Typography variant="subtitle1" gutterBottom>관심 키워드</Typography>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
            {(user?.interests || []).map((k) => (
              <span key={k} className="bk-badge" style={{ cursor: 'pointer' }} onClick={() => handleRemoveInterest(k)}>
                {k} ✕
              </span>
            ))}
            {(!user?.interests || user.interests.length === 0) && (
              <Typography variant="body2" color="text.secondary">아직 없음 — 추가해보세요</Typography>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <TextField size="small" placeholder="예: 예산, 외교" value={newInterest} onChange={(e) => setNewInterest(e.target.value)} />
            <Button variant="outlined" onClick={handleAddInterest}>추가</Button>
          </div>
        </div>
```
그리고 컴포넌트 상단에 상태/핸들러 추가:
```jsx
  const { changePassword, deleteAccount, updateInterests } = useMyPage(user);
  const { setUser } = useAppContext();
  const [newInterest, setNewInterest] = useState("");

  const saveInterests = async (interests) => {
    try {
      await updateInterests(interests);
      const updated = { ...user, interests };
      setUser(updated);
      localStorage.setItem("user", JSON.stringify(updated));
      toast.success("관심 키워드 저장됨");
    } catch (err) {
      toast.error("저장 실패: " + (err.message || ""));
    }
  };
  const handleAddInterest = () => {
    const k = newInterest.trim();
    if (!k) return;
    const cur = user?.interests || [];
    if (cur.includes(k)) { setNewInterest(""); return; }
    saveInterests([...cur, k]);
    setNewInterest("");
  };
  const handleRemoveInterest = (k) => {
    saveInterests((user?.interests || []).filter((x) => x !== k));
  };
```
(MyPage 상단 import에 `useAppContext` 추가: `import { useAppContext } from "./AppContext";`)

- [ ] **Step 3: 빌드** — `CI=false npm run build 2>&1 | grep -E "Compiled|Failed"` → Compiled successfully.

- [ ] **Step 4: Commit**
```bash
git add src/components/MyPage.jsx src/hooks/useMyPage.js
git commit -m "feat(digest): MyPage 관심 키워드 편집 (저장 + 컨텍스트 반영)"
```

---

## Self-Review
- 스펙 커버리지: 매칭로직(T1)·digest API(T1,T2)·맞춤 탭(T3)·관심 편집(T4). 인앱 개인화 다이제스트 완결.
- 매칭은 pytest, digest는 실 Firestore, 프론트는 빌드.
- 타입 일관성: `matches_interests`→`get_digest`(data.articles)→`getDigest`(res.data.data.articles)→useDigest→맞춤 탭. `updateInterests`→PUT /api/auth/profile(interests)→user.interests.
- 라우트 순서 주의: `/digest`는 `/{article_id}` 앞.
- FCM 실제 푸시는 배포 후 별도(디바이스 토큰 등록 endpoint 포함).

## 다음
실제 FCM 푸시(배포·디바이스 토큰 후), 또는 #2~#5 외 추가 개선.
