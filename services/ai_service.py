import asyncio
import google.generativeai as genai
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
from firebase.firebase_config import db
import traceback

class AISummaryService:
    # def __init__(self):
    #     self.client = OpenAI(
    #         api_key=os.getenv("OPENAI_API_KEY")
    #     )
    #     print(self.client)
    #     self.model = "gpt-3.5-turbo"
    #     self.max_tokens = 100
    
    async def safe_summarize(title, summary, max_retries=3):
        for attempt in range(max_retries):
            try:
                return await ai_summary_service.summarize_article(title, summary)
            except Exception as e:
                wait = 10 * (attempt + 1)
                print(f"429 에러 발생, {wait}초 후 재시도...")
                await asyncio.sleep(wait)
        return {"success": False, "message": "요약 실패"}

    async def summarize_article(self, title: str, content: str = "") -> Dict[str, Any]:
        """개별 기사 요약"""
        try:
            # 요약할 텍스트 준비
            text_to_summarize = f"제목: {title}\n내용: {content}" if content else f"제목: {title}"
            print("ai 요약할 내용"+text_to_summarize)
            # OpenAI API 호출
            print("Loaded API Key:", os.getenv("GOOGLE_API_KEY"))
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            prompt = f"""
                당신은 한국 정치 뉴스 전문 요약 AI입니다. 주어진 뉴스 기사를 2-3문장으로 핵심만 간결하게 요약해주세요. 객관적이고 중립적인 톤을 유지하세요.
                \n\n다음 정치 뉴스를 요약해주세요:\n\n{text_to_summarize}

                위 내용을 2~3문장으로 객관적이고 중립적으로 요약해 주세요.
                """
            
            model = genai.GenerativeModel('gemini-2.5-pro')
            response = model.generate_content(prompt)
            print("ai 요약결과:", response.text) 
            
            summary = response.text.strip()

            return {
                "success": True,
                "data": {"summary": summary}
            }

        except Exception as e:
            traceback.print_exc()
            return {
                "success": False,
                "message": f"AI 요약 생성 중 오류가 발생했습니다: {str(e)}"
            }

    async def generate_daily_summary(self, date: str = None) -> Dict[str, Any]:
        """일일 정치 뉴스 요약 생성"""
        try:
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")

            # 해당 날짜의 기사들 조회
            articles = await self._get_articles_by_date(date)

            if not articles:
                return {
                    "success": False,
                    "message": "해당 날짜의 기사가 없습니다."
                }

            # 카테고리별로 기사 분류
            categorized_articles = self._categorize_articles(articles)

            # AI를 통한 종합 요약 생성
            comprehensive_summary = await self._generate_comprehensive_summary(categorized_articles)

            # 주요 하이라이트 추출
            highlights = await self._extract_highlights(articles)

            # 일일 요약 데이터 구성
            daily_summary = {
                "id": f"summary_{date}",
                "date": date,
                "highlights": highlights,
                "comprehensive_summary": comprehensive_summary,
                "categories": categorized_articles,
                "total_articles": len(articles),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Firestore에 저장
            db.collection("daily_summaries").document(daily_summary["id"]).set(daily_summary)

            return {
                "success": True,
                "message": "일일 요약이 생성되었습니다.",
                "data": daily_summary
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"일일 요약 생성 중 오류가 발생했습니다: {str(e)}"
            }

    async def _get_articles_by_date(self, date: str) -> List[Dict[str, Any]]:
        """특정 날짜의 기사들 조회"""
        try:
            # 날짜 범위 설정 (해당 날짜 00:00:00 ~ 23:59:59)
            start_date = datetime.strptime(date, "%Y-%m-%d")
            end_date = start_date + timedelta(days=1)

            articles_ref = db.collection("articles")
            query = articles_ref.where("published_at", ">=", start_date).where("published_at", "<", end_date)

            docs = query.stream()
            return [doc.to_dict() for doc in docs]

        except Exception as e:
            print(f"날짜별 기사 조회 오류: {e}")
            return []

    def _categorize_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """기사들을 카테고리별로 분류"""
        categories = {
            "president": [],
            "parliament": [],
            "politics": [],
            "breaking": []
        }

        for article in articles:
            category = article.get("category", "politics")
            if category in categories:
                categories[category].append({
                    "title": article["title"],
                    "summary": article["summary"],
                    "source": article["source"],
                    "source_url": article["source_url"]
                })

        return categories

    async def _generate_comprehensive_summary(self, categorized_articles: Dict[str, List[Dict[str, Any]]]) -> str:
        """카테고리별 기사들의 종합 요약 생성"""
        try:
            # 각 카테고리의 기사 제목들을 수집
            category_summaries = []

            for category, articles in categorized_articles.items():
                if articles:
                    category_name = {
                        "president": "대통령 관련",
                        "parliament": "국회 관련", 
                        "politics": "정치 일반",
                        "breaking": "주요 속보"
                    }.get(category, category)

                    titles = [article["title"] for article in articles[:5]]  # 최대 5개까지
                    category_text = f"{category_name}: " + ", ".join(titles)
                    category_summaries.append(category_text)

            if not category_summaries:
                return "오늘은 주요 정치 뉴스가 없었습니다."

            # OpenAI를 통한 종합 요약
            prompt = f"""
            다음은 오늘의 한국 정치 뉴스 제목들입니다. 이를 바탕으로 하루의 정치 상황을 3-4문장으로 종합 요약해주세요:
            {chr(10).join(category_summaries)}
            요약 시 다음 사항을 고려해주세요:
            1. 가장 중요한 이슈를 우선적으로 언급
            2. 객관적이고 중립적인 톤 유지
            3. 정치적 편향 없이 사실 중심으로 서술
            """

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 한국 정치 전문 기자입니다. 하루의 정치 뉴스를 종합하여 객관적이고 간결한 요약을 제공합니다."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=300,
                temperature=0.3
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            return f"종합 요약 생성 중 오류가 발생했습니다: {str(e)}"

    async def _extract_highlights(self, articles: List[Dict[str, Any]]) -> List[str]:
        """주요 하이라이트 추출"""
        try:
            # 중요 키워드가 포함된 기사들을 우선 선별
            important_keywords = ["대통령", "국회", "법안", "정책", "선거", "개혁", "특검", "예산"]

            highlighted_articles = []
            for article in articles:
                title = article["title"]
                score = sum(1 for keyword in important_keywords if keyword in title)
                if score > 0:
                    highlighted_articles.append((article, score))

            # 점수순으로 정렬하여 상위 5개 선택
            highlighted_articles.sort(key=lambda x: x[1], reverse=True)
            highlights = []

            for article, _ in highlighted_articles[:5]:
                highlights.append(f"• {article['title']}")

            return highlights if highlights else ["오늘은 특별한 정치 이슈가 없었습니다."]

        except Exception as e:
            return [f"하이라이트 추출 중 오류가 발생했습니다: {str(e)}"]

    async def get_daily_summary(self, date: str = None) -> Dict[str, Any]:
        """일일 요약 조회"""
        try:
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")

            summary_id = f"summary_{date}"
            doc_ref = db.collection("daily_summaries").document(summary_id)
            doc = doc_ref.get()

            if doc.exists:
                return {
                    "success": True,
                    "data": doc.to_dict()
                }
            else:
                # 요약이 없으면 자동 생성
                return await self.generate_daily_summary(date)

        except Exception as e:
            return {
                "success": False,
                "message": f"일일 요약 조회 중 오류가 발생했습니다: {str(e)}"
            }

# AI 요약 서비스 인스턴스 생성
ai_summary_service = AISummaryService()