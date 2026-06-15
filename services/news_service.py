from datetime import datetime
try:
    import feedparser
except ImportError:
    feedparser = None
import time
from typing import List, Dict, Any, Optional
from firebase.firebase_config import db
from google.cloud import firestore
from models.enum import ArticleCategory
import hashlib
import re
from services.ai_service import ai_summary_service
import asyncio
import requests
from utils.collect_config import ai_throttle_seconds
from utils.article_fetch import fetch_article_text
from utils.digest import matches_interests
from utils.gemini_rest import parse_query, synthesize_briefing
from utils.search_rank import rank_articles
from utils.personalize import build_profile, pick_reason, diversify
from models.model import President, ParliamentaryActivity, PoliticalStatement
from dateutil import parser as dateparser

class NewsService:
    def __init__(self):
        self.rss_feeds = {
            "정치": [
                "https://www.yna.co.kr/rss/politics.xml", # 연합뉴스 정치
                "https://www.yonhapnewstv.co.kr/category/news/politics/feed/", # 연합뉴스TV 정치
                "https://rss.hankyung.com/politics.xml", # 한국경제 정치
                "http://www.segye.com/Articles/RSSFeed/Politics.xml", # 세계일보 정치
                "http://www.hani.co.kr/rss/politics/", # 한겨레 정치
                "https://rss.donga.com/politics.xml",  # 동아일보 정치
                "https://feeds.bbci.co.uk/korean/rss.xml",  # BBC 코리아 (외신)
                "http://www.khan.co.kr/rss/rssdata/politic_news.xml",  # 경향신문 정치
                "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01",  # SBS 정치
                "http://rss.ohmynews.com/rss/politics.xml",  # 오마이뉴스 정치
            ],
            "대통령": [
                "https://www.korea.kr/rss/president.xml",  # 대통령실 공식
            ],
            "정책": [
                "https://www.korea.kr/rss/policy.xml",  # 정책 뉴스
            ],
            "정부": [
                "https://www.korea.kr/rss/ebriefing.xml",  # 정부 브리핑
            ]
        }
        self.request_delay = 3  # RSS 요청 간 3초 지연

    def _clean_source(self, raw_source: str, url: str = "") -> str:
        """RSS의 feed.title 또는 출처 텍스트를 정제"""
        # 우선 URL 도메인을 기준으로 정리
        domain_map = {
            "yna.co.kr": "연합뉴스", "yonhapnewstv.co.kr": "연합뉴스",
            "hankyung.com": "한국경제", "segye.com": "세계일보",
            "hani.co.kr": "한겨레", "donga.com": "동아일보",
            "sedaily.com": "서울경제",
            "bbc.co.uk": "BBC 코리아", "bbci.co.uk": "BBC 코리아",
            "khan.co.kr": "경향신문", "sbs.co.kr": "SBS", "ohmynews.com": "오마이뉴스",
            "president": "대통령실", "policy": "정책 뉴스", "ebriefing": "부처별 브리핑"
        }

        for domain, name in domain_map.items():
            if domain in url:
                return name
        return raw_source.split(":")[0].strip()
    
    def _extract_image_url(self, entry: dict) -> str:
        # 1. media_content 필드 (일반적으로 신뢰도가 높음)
        media_content = entry.get("media_content", [])
        if media_content and isinstance(media_content, list):
            url = media_content[0].get("url", "")
            if url:
                return url

        # 2. enclosure 필드 (일부 RSS에서 사용)
        if "enclosure" in entry and isinstance(entry["enclosure"], dict):
            url = entry["enclosure"].get("url", "")
            if url:
                return url

        # 3. entry.links에서 이미지 타입 찾기 (rel="enclosure" 또는 type이 image인 경우)
        if "links" in entry:
            for link in entry["links"]:
                if (link.get("rel") == "enclosure" or "image" in link.get("type", "")):
                    url = link.get("href", "")
                    if url:
                        return url

        # 4. content:encoded 내 <img src="...">
        content = entry.get("content", [{}])
        if content and isinstance(content, list):
            raw_html = content[0].get("value", "")
            match = re.search(r'<img[^>]+src=["\'](.*?)["\']', raw_html)
            if match:
                return match.group(1)

        # 5. summary 내 <img src="...">
        summary = entry.get("summary", "")
        if summary:
            match = re.search(r'<img[^>]+src=["\'](.*?)["\']', summary)
            if match:
                return match.group(1)

        return ""  # 못 찾은 경우 빈 문자열

    def _generate_article_id(self, title: str, source_url: str) -> str:
        """기사 고유 ID 생성"""
        content = f"{title}{source_url}"
        return hashlib.md5(content.encode()).hexdigest()

    def _clean_text(self, text: str) -> str:
        """텍스트 정리 (HTML 태그 제거 등)"""
        # HTML 태그 제거
        clean = re.compile('<.*?>')
        text = re.sub(clean, '', text)

        # 연속된 공백 제거
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def _categorize_article(self, title: str, summary: str) -> ArticleCategory:
        """기사 카테고리 자동 분류"""
        content = (title + " " + summary).lower()

        # 키워드 기반 분류
        if any(keyword in content for keyword in ["대통령", "이재명", "대통령실", "청와대"]):
            return ArticleCategory.PRESIDENT
        elif any(keyword in content for keyword in ["국회", "의원", "법안", "국정감사", "본회의"]):
            return ArticleCategory.PARLIAMENT
        elif any(keyword in content for keyword in ["속보", "긴급", "중대", "발표"]):
            return ArticleCategory.BREAKING
        else:
            return ArticleCategory.POLITICS

    def _extract_keywords(self, title: str, summary: str) -> List[str]:
        """키워드 추출"""
        # 기본적인 키워드 추출 (실제로는 더 정교한 NLP 사용 가능)
        keywords = []
        content = title + " " + summary

        # 정치 관련 주요 키워드
        political_keywords = [
            "대통령", "국회", "정부", "여당", "야당", "민주당", "국민의힘", 
            "법안", "정책", "개혁", "선거", "정치", "국정감사", "예산", "특검"
        ]

        for keyword in political_keywords:
            if keyword in content:
                keywords.append(keyword)

        return list(set(keywords))  # 중복 제거

    async def collect_news_from_rss(self, category: str = None) -> Dict[str, Any]:
        try:
            if feedparser is None:
                return {"success": False, "message": "수집 비활성(feedparser 미설치). 수집은 GitHub Actions에서 실행."}
            collected_articles = []
            collected_presidents = []
            collected_parliamentary = []
            collected_statements = []

            feeds_to_process = self.rss_feeds.items() if not category else [(category, self.rss_feeds.get(category, []))]

            for category_name, feed_urls in feeds_to_process:
                for feed_url in feed_urls:
                    try:
                        response = requests.get(feed_url)
                        response.encoding = 'utf-8'
                        feed = feedparser.parse(response.text)
                        if feed.bozo:
                            print(f"Error parsing feed {feed_url}: {feed.bozo_exception}")
                            continue

                        for entry in feed.entries[:10]:
                            title = self._clean_text(entry.get('title', ''))
                            summary = self._clean_text(entry.get('summary', ''))[:300]
                            source_url = entry.get('link', '')
                            source_raw = feed.feed.get('title', 'Unknown')
                            source = self._clean_source(source_raw, source_url)
                            image_url = self._extract_image_url(entry)

                            if not (title and source_url):
                                continue

                            article_id = self._generate_article_id(title, source_url)

                            # 중복 확인 (카테고리별 대상 컬렉션에서)
                            if await self._doc_exists(self._target_collection(category_name), article_id):
                                continue

                            # 기사 본문 크롤링 (실패 시 RSS 요약으로 폴백)
                            body = await asyncio.to_thread(fetch_article_text, source_url)
                            content = body or summary

                            ai_result = await ai_summary_service.summarize_by_category(category_name, title, content)
                            await asyncio.sleep(ai_throttle_seconds())
                            if not ai_result["success"]:
                                print(f"AI 요약 실패: {ai_result['message']}")
                                continue
                            # ai_summary = ai_result["data"]["summary"] if ai_result["success"] else ""
                            
                            ai_data = ai_result["data"]

                            # 정책
                            if category_name == "정책":
                                policy_data = ParliamentaryActivity(
                                    title=title,
                                    context= ai_data.get("context", ""),
                                    type= ai_data.get("type", ""),
                                    date=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                    status= ai_data.get("status", ""),
                                    proposer=ai_data.get("proposer", None),
                                    category=ai_data.get("category", ""),
                                    committee=ai_data.get("committee", None),
                                    bill_number= ai_data.get("bill_number", None),
                                    description=content,
                                    related_links=[source_url],
                                    created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                                ). dict()
                                db.collection("parliamentary_activities").document(article_id).set(policy_data)
                                collected_parliamentary.append(policy_data)
                            elif category_name == "대통령":
                                president_data = President(
                                    id = article_id,
                                    title=title,
                                    context= ai_data.get("context", ""),
                                    promise_type= ai_data.get("promise_type", ""),
                                    status= ai_data.get("status", ""),
                                    category= ai_data.get("category", ""),
                                    progress= ai_data.get("progress", None),
                                    last_update=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                    related_links=[source_url],
                                    date=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                    created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                                ).dict()

                                db.collection("presidents").document(article_id).set(president_data)
                                collected_presidents.append(president_data)
                            elif category_name == "정부":
                                # 정부 브리핑은 뉴스 엔티티에 저장
                                article_data = {
                                    "id": article_id,
                                    "title": title,
                                    "ai_summary": ai_data.get("ai_summary", ""),
                                    "source": source,
                                    "source_url": source_url,
                                    "image_url": image_url,
                                    "category": ArticleCategory.GOVERNMENT.value,
                                    "keywords": self._extract_keywords(title, summary),
                                    "published_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                    "created_at": datetime.utcnow(),
                                    "updated_at": datetime.utcnow(),
                                    "view_count": 0,
                                    "bookmark_count": 0
                                }
                                db.collection("articles").document(article_id).set(article_data)
                                collected_articles.append(article_data)
                            elif category_name == "정치":
                                # 기본 정치 뉴스는 뉴스 엔티티에 저장
                                article_data = {
                                    "id": article_id,
                                    "title": title,
                                    "ai_summary": ai_data.get("ai_summary", ""),
                                    "source": source,
                                    "source_url": source_url,
                                    "image_url": image_url,
                                    "category": category_name,
                                    "keywords": self._extract_keywords(title, summary),
                                    "published_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                    "created_at": datetime.utcnow(),
                                    "updated_at": datetime.utcnow(),
                                    "view_count": 0,
                                    "bookmark_count": 0
                                }
                                db.collection("articles").document(article_id).set(article_data)
                                collected_articles.append(article_data)

                                # 정치 기사에서 정치인 발언 2차 추출 (발언자 식별 시 저장)
                                stmt_res = await ai_summary_service.summarize_by_category("정치인발언", title, content)
                                if stmt_res.get("success"):
                                    sd = stmt_res["data"]
                                    speaker = (sd.get("speaker") or "").strip()
                                    if speaker and speaker.lower() != "none":
                                        statement_id = self._generate_article_id(speaker, sd.get("context", "") or "")
                                        if not await self._doc_exists("political_statements", statement_id):
                                            statement_data = PoliticalStatement(
                                                speaker=speaker,
                                                party=sd.get("party", "") or "",
                                                speak_reason=sd.get("speak_reason", "") or "",
                                                context=sd.get("context", "") or "",
                                                category=sd.get("category", "") or "",
                                                type=sd.get("type", "") or "",
                                                related_links=[source_url],
                                                date=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                                            ).dict()
                                            db.collection("political_statements").document(statement_id).set(statement_data)
                                            collected_statements.append(statement_data)
                                    await asyncio.sleep(ai_throttle_seconds())
                            # AI 정치인 발언 추출 (예시: ai_result에 정치인 발언 정보가 있을 경우)
                            else:
                                statement_id = self._generate_article_id(ai_data.get("speaker", ""), ai_data.get("context", ""))
                                statement_data = PoliticalStatement(
                                    speaker=ai_data.get("speaker", ""),
                                    party=ai_data.get("party", ""),
                                    speak_reason= ai_data.get("speak_reason", ""),
                                    context=ai_data.get("context", ""),
                                    category= ai_data.get("category", ""),
                                    type= ai_data.get("type", ""),
                                    related_links=[source_url],
                                    date=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                    created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                                ).dict()
                                db.collection("political_statements").document(statement_id).set(statement_data)
                                collected_statements.append(statement_data)
                                continue  # 정치인 발언은 기사 저장에서 제외

                        await asyncio.sleep(self.request_delay)

                    except Exception as e:
                        print(f"RSS 피드 처리 오류 ({feed_url}): {e}")
                        continue

            return {
                "success": True,
                "message": "수집 완료",
                "data": {
                    "articles": collected_articles[:5],
                    "presidents": collected_presidents[:5],
                    "parliamentary_activities": collected_parliamentary[:5],
                    "statements": collected_statements[:5]
                }
            }

        except Exception as e:
            return {"success": False, "message": f"뉴스 수집 중 오류가 발생했습니다: {str(e)}"}
    
    def _get_collection_name(self, category_name: str) -> str:
        if category_name == "대통령":
            return "presidents"
        elif category_name == "정책":
            return "parliamentary_activities"
        elif category_name in ["정치인발언"]:
            return "statements"
        else:
            return "articles"

    async def _is_article_exists(self, article_id: str) -> bool:
        """기사 중복 확인"""
        try:
            doc_ref = db.collection("articles").document(article_id)
            doc = doc_ref.get()
            return doc.exists
        except:
            return False

    def _target_collection(self, category_name: str) -> str:
        """카테고리별 저장 대상 컬렉션."""
        return {
            "대통령": "presidents",
            "정책": "parliamentary_activities",
        }.get(category_name, "articles")

    async def _doc_exists(self, collection_name: str, doc_id: str) -> bool:
        """지정 컬렉션에 문서 존재 여부."""
        try:
            return db.collection(collection_name).document(doc_id).get().exists
        except Exception:
            return False

    async def get_articles(self, 
                          category: Optional[str] = None, 
                          limit: int = 20, 
                          offset: int = 0) -> Dict[str, Any]:
        """기사 목록 조회"""
        try:
            articles_ref = db.collection("articles")

            # 카테고리 필터
            if category:
                query = articles_ref.where("category", "==", category)
            else:
                print("카테고리 필터 없음")
                query = articles_ref

            # 정렬 및 페이징
            query = query.order_by("published_at", direction=firestore.Query.DESCENDING)
            query = query.limit(limit).offset(offset)

            docs = query.stream()
            articles = [doc.to_dict() for doc in docs]

            return {
                "success": True,
                "message": "뉴스 목록 조회 성공",
                "data": {"articles": articles, "count": len(articles)}
            }

        except Exception as e:
            return {"success": False, "message": f"기사 조회 중 오류가 발생했습니다: {str(e)}"}

    async def ai_search(self, query: str, include_briefing: bool = False,
                        limit: int = 20, candidate_pool: int = 300) -> Dict[str, Any]:
        """자연어 검색: Gemini로 질의 구조화 → 후보 기사 랭킹 → (옵션)브리핑.
        Gemini가 없거나 실패하면 부분문자열 폴백으로 동작(앱이 깨지지 않음)."""
        import time as _time
        from datetime import datetime, timezone
        t0 = _time.monotonic()
        try:
            # 1) 후보 기사 로드(최근순). Firestore stream은 동기 I/O라 스레드로 오프로드.
            def _load():
                docs = (db.collection("articles")
                        .order_by("published_at", direction=firestore.Query.DESCENDING)
                        .limit(candidate_pool).stream())
                return [doc.to_dict() for doc in docs]
            candidates = await asyncio.to_thread(_load)

            # 2) Gemini 질의 구조화(실패 시 폴백)
            parsed, reason = await parse_query(query)
            ai_used = parsed is not None

            # 3) 랭킹
            ranked = rank_articles(candidates, parsed, query, limit=limit,
                                   now=datetime.now(timezone.utc))

            # 4) 옵션 브리핑(상위 결과 기반)
            briefing = None
            brief_reason = None
            if include_briefing and ranked:
                briefing, brief_reason = await synthesize_briefing(query, ranked)

            latency_ms = int((_time.monotonic() - t0) * 1000)
            return {
                "success": True,
                "message": "AI 검색 성공",
                "data": {
                    "query": query,
                    "mode": "ai_structured" if ai_used else "fallback_keyword",
                    "ai": {"used": ai_used, "cached": reason == "cache",
                           "fallback_reason": None if ai_used else reason,
                           "briefing_requested": include_briefing, "briefing_reason": brief_reason,
                           "latency_ms": latency_ms},
                    "parsed": parsed,
                    "items": ranked,
                    "count": len(ranked),
                    "briefing": briefing,
                },
            }
        except Exception as e:
            print(f"[ai_search] error: {e!r}")  # 상세는 로그로만
            return {"success": False, "message": "AI 검색 중 오류가 발생했습니다."}

    async def personalized_feed(self, user_id: str, interests, limit: int = 30,
                                candidate_pool: int = 300) -> Dict[str, Any]:
        """개인 맞춤 'For You' 피드. 순수 랭킹(Gemini 미사용) + 다양성 강제 + 추천 사유.
        관심사·북마크가 모두 없으면 '시작 추천'(최신+다양성) 모드로 정직하게 처리."""
        from datetime import datetime, timezone
        try:
            def _load_recent():
                docs = (db.collection("articles")
                        .order_by("published_at", direction=firestore.Query.DESCENDING)
                        .limit(candidate_pool).stream())
                return [doc.to_dict() for doc in docs]

            def _load_bookmark_articles():
                if not user_id:
                    return []
                try:
                    # order_by 없이 단일 필터(복합 인덱스 회피). 키워드 추출엔 순서 불필요.
                    bms = (db.collection("bookmarks")
                           .where("user_id", "==", user_id).limit(30).stream())
                    ids = [bm.to_dict().get("article_id") for bm in bms]
                    refs = [db.collection("articles").document(a) for a in ids if a]
                    if not refs:
                        return []
                    # 배치 조회(개별 get N회 → 1회 get_all)
                    return [d.to_dict() for d in db.get_all(refs) if d.exists]
                except Exception as be:  # 북마크 조회 실패해도 관심사만으로 개인화 지속
                    print(f"[personalized_feed] bookmark load skipped: {be!r}")
                    return []

            candidates = await asyncio.to_thread(_load_recent)
            bookmark_articles = await asyncio.to_thread(_load_bookmark_articles)

            parsed, explicit, implicit = build_profile(interests, bookmark_articles)
            has_profile = bool(parsed["keywords"])

            ranked = []
            if has_profile:
                ranked = rank_articles(candidates, parsed, query="", limit=candidate_pool,
                                       now=datetime.now(timezone.utc))
                ranked = diversify(ranked, limit=limit)
                for it in ranked:
                    it["reason"] = pick_reason(it, explicit, implicit)

            if ranked:
                mode = "personalized"
            else:
                # 콜드스타트 또는 관심사 매칭 0건 → '맞춤' 아닌 '시작 추천'으로 정직하게(codex)
                mode = "no_match" if has_profile else "starter"
                ranked = diversify(list(candidates), limit=limit)
                for it in ranked:
                    it["reason"] = "지금 주목받는 정치뉴스"

            return {
                "success": True,
                "message": "맞춤 피드 조회 성공",
                "data": {
                    "mode": mode,
                    "profile": {"explicit": explicit, "implicit": implicit},
                    "items": ranked,
                    "count": len(ranked),
                },
            }
        except Exception as e:
            print(f"[personalized_feed] error: {e!r}")
            return {"success": False, "message": "맞춤 피드 조회 중 오류가 발생했습니다."}

    async def search_articles(self,
                             query: str,
                             category: Optional[str] = None,
                             limit: int = 20) -> Dict[str, Any]:
        """기사 검색"""
        try:
            articles_ref = db.collection("articles")

            # 기본적인 제목 검색 (Firestore의 제한으로 인해 간단한 구현)
            # 실제 프로덕션에서는 Elasticsearch 등 사용 권장
            if category:
                docs = articles_ref.where("category", "==", category).stream()
            else:
                docs = articles_ref.stream()

            # 클라이언트 사이드 필터링 (제목과 요약에서 검색)
            matched_articles = []
            for doc in docs:
                article = doc.to_dict()
                if (query.lower() in article.get("title", "").lower() or 
                    query.lower() in article.get("ai_summary", "").lower()):
                    matched_articles.append(article)

                if len(matched_articles) >= limit:
                    break

            return {
                "success": True,
                "message": "기사 검색 성공",
                "data": {"articles": matched_articles, "query": query, "count": len(matched_articles)}
            }

        except Exception as e:
            return {"success": False, "message": f"기사 검색 중 오류가 발생했습니다: {str(e)}"}

    async def get_article_by_id(self, article_id: str) -> Dict[str, Any]:
        """특정 기사 조회"""
        try:
            doc_ref = db.collection("articles").document(article_id)
            doc = doc_ref.get()

            if doc.exists:
                article = doc.to_dict()

                # 조회수 증가
                doc_ref.update({"view_count": article.get("view_count", 0) + 1})
                article["view_count"] = article.get("view_count", 0) + 1

                return {"success": True, "data": {"article": article}}
            else:
                return {"success": False, "message": "기사를 찾을 수 없습니다."}

        except Exception as e:
            return {"success": False, "message": f"기사 조회 중 오류가 발생했습니다: {str(e)}"}

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


# 뉴스 서비스 인스턴스 생성
news_service = NewsService()