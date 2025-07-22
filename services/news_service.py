from datetime import datetime
import feedparser
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

class NewsService:
    def __init__(self):
        self.rss_feeds = {
            "정치": [
                "https://www.yna.co.kr/rss/politics.xml" # 연합뉴스 정치
                "https://www.yonhapnewstv.co.kr/category/news/politics/feed/", # 연합뉴스TV 정치
                "https://rss.hankyung.com/politics.xml", # 한국경제 정치
                "http://www.segye.com/Articles/RSSFeed/Politics.xml", # 세계일보 정치
                "http://www.hani.co.kr/rss/politics/", # 한겨레 정치
                "https://rss.donga.com/politics.xml",  # 동아일보 정치
            ],
            "대통령": [
                "https://www.korea.kr/rss/president.xml",  # 대통령실 공식
            ],
            "정책": [
                "https://www.korea.kr/rss/policy.xml",  # 정책 뉴스
            ],
            "부처별": [
                "https://www.korea.kr/rss/ebriefing.xml",  # 부처별 브리핑
            ]
        }
        self.request_delay = 3  # RSS 요청 간 3초 지연

    def _clean_source(self, raw_source: str, url: str = "") -> str:
        """RSS의 feed.title 또는 출처 텍스트를 정제"""
        # 우선 URL 도메인을 기준으로 정리
        domain_map = {
            "yna.co.kr": "연합뉴스",
            "yonhapnewstv.co.kr": "연합뉴스",
            "hankyung.com": "한국경제",
            "segye.com": "세계일보",
            "hani.co.kr": "한겨레",
            "donga.com": "동아일보",
            "sedaily.com": "서울경제",
            "president": "대통령실",
            "policy": "정책 뉴스",
            "ebriefing": "부처별 브리핑"
        }

        for domain, name in domain_map.items():
            if domain in url:
                return name

        # fallback: ":" 기준 앞부분 사용
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
        """RSS 피드에서 뉴스 수집"""
        try:
            collected_articles = []
            feeds_to_process = self.rss_feeds.items() if not category else [(category, self.rss_feeds.get(category, []))]

            for category_name, feed_urls in feeds_to_process:
                for feed_url in feed_urls:
                    try:
                        # RSS 피드 파싱
                        response = requests.get(feed_url)
                        response.encoding = 'utf-8'  # 강제 인코딩
                        feed = feedparser.parse(response.text)
                        if feed.bozo:
                            print(f"Error parsing feed {feed_url}: {feed.bozo_exception}")
                            continue

                        for entry in feed.entries[:10]:  # 최신 10개 기사만 수집
                            print(entry)  # 디버깅용 출력
                            # 기사 정보 추출
                            title = self._clean_text(entry.get('title', ''))
                            summary = self._clean_text(entry.get('summary', ''))[:300]  # 300자로 제한
                            source_url = entry.get('link', '')
                            source_raw = feed.feed.get('title', 'Unknown')
                            source = self._clean_source(source_raw, source_url)
                            image_url = self._extract_image_url(entry)

                            # 필수 정보가 있는 경우만 처리
                            if title and source_url:
                                article_id = self._generate_article_id(title, source_url)

                                # 중복 확인
                                if not await self._is_article_exists(article_id):
                                    ai_result = await ai_summary_service.summarize_article(title, summary)
                                    await asyncio.sleep(15)  # AI 요청 간 지연
                                    ai_summary = ai_result["data"]["summary"] if ai_result["success"] else ""
                                    published = entry.get('published_parsed')
                                    published_at = (datetime(*published[:6]) if isinstance(published, tuple) else datetime.now())
                                    article_data = {
                                        "id": article_id,
                                        "title": title,
                                        "ai_summary": ai_summary,
                                        "source": source,
                                        "source_url": source_url,
                                        "image_url": image_url,
                                        "category": self._categorize_article(title, summary).value,
                                        "keywords": self._extract_keywords(title, summary),
                                        "published_at": published_at,
                                        "created_at": datetime.utcnow(),
                                        "updated_at": datetime.utcnow(),
                                        "view_count": 0,
                                        "bookmark_count": 0
                                    }

                                    collected_articles.append(article_data)

                        # 요청 간 지연
                        time.sleep(self.request_delay)

                    except Exception as e:
                        print(f"RSS 피드 처리 오류 ({feed_url}): {e}")
                        continue

            # Firestore에 저장
            saved_count = 0
            for article in collected_articles:
                try:
                    db.collection("articles").document(article["id"]).set(article)
                    saved_count += 1
                except Exception as e:
                    print(f"기사 저장 오류: {e}")

            return {
                "success": True,
                "message": f"{saved_count}개의 새 기사가 수집되었습니다.",
                "data": {"collected_count": saved_count, "articles": collected_articles[:5]}  # 최근 5개만 반환
            }

        except Exception as e:
            return {"success": False, "message": f"뉴스 수집 중 오류가 발생했습니다: {str(e)}"}

    async def _is_article_exists(self, article_id: str) -> bool:
        """기사 중복 확인"""
        try:
            doc_ref = db.collection("articles").document(article_id)
            doc = doc_ref.get()
            return doc.exists
        except:
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
                    query.lower() in article.get("summary", "").lower()):
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

# 뉴스 서비스 인스턴스 생성
news_service = NewsService()