import asyncio
import google.generativeai as genai
import os
import re
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from firebase.firebase_config import db
from google.cloud import firestore
import traceback
from utils.ai_parsing import extract_json_block

class AISummaryService:
    def __init__(self):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.model = genai.GenerativeModel(self.model_name)
    
    async def summarize_by_category(self, category, title, summary, max_retries=3):
        last = {"success": False, "message": "요약 실패"}
        for attempt in range(max_retries):
            try:
                result = await self.summarize_by_category2(category, title, summary)
                if result.get("success"):
                    return result
                last = result
            except Exception as e:
                last = {"success": False, "message": str(e)}
            if attempt < max_retries - 1:
                await asyncio.sleep(2 * (attempt + 1))
        return last

    # ===== 프롬프트 빌더 =====
    def _build_prompt(self, category: str, title: str, content: str) -> str:
        """카테고리에 따라 적절한 프롬프트를 생성합니다."""
        prompt_map = {
            "대통령": self._build_president_prompt,
            "정책": self._build_policy_prompt,
            "정치인발언": self._build_statement_prompt,
            "정치": self._build_general_politics_prompt,
            "정부": self._build_general_politics_prompt
        }
        return prompt_map.get(category, self._build_general_politics_prompt)(title, content)

    def _build_president_prompt(self, title: str, content: str) -> str:
        return f"""
        당신은 한국 정치 전문 기자이자 데이터 분석가입니다.
        아래 대통령 관련 뉴스를 읽고, 다음 JSON 형식으로 반환하세요.
        단 # 이 적혀있는 컬럼들은 해당 내용들을 반드시 준수하고 정보를 찾기 힘들경우 None로 반환하세요.

        {{
            "context": "..." # 요약 내용,
            "promise_type": "..." # 약속 유형 (예: "공약", "정책"), 
            "status": "..." # 약속 상태 (예: "이행 중", "완료", "미이행"), 
            "category": "..." # 약속 카테고리 (예: "경제", "사회", "정치"), 
            "progress": "..." # 진행 상황 (예: "50% 완료"),
        }}

        반드시 JSON만 반환하세요.
        
        제목: {title}
        내용: {content}
        """

    def _build_policy_prompt(self, title: str, content: str) -> str:
        return f"""
        당신은 국회 전문 기자이자 데이터 분석가입니다.
        아래 정책 뉴스를 읽고, 다음 JSON 형식으로 반환하세요.
        단 # 이 적혀있는 컬럼들은 해당 내용들을 반드시 준수하고 정보를 찾기 힘들경우 None로 반환하세요.

        {{
            "context": "..." # 요약 내용,
            "type": "..." # 활동 유형 (예: "회의", "토론", "법안 심사"),
            "status": "..." # 법안 상태 (예: "발의", "가결", "심사 중" "통과"),
            "proposer": "..." # 발의자 또는 발의자 그룹,
            "category": "..." # 법안 카테고리 (예: "경제", "사회", "정치"),
            "committee": "..." # 소관 위원회,
            "bill_number": "..." # 법안 번호,
            "description": "..." # 법안 설명
        }}

        반드시 JSON만 반환하세요.
        
        제목: {title}
        내용: {content}
        """

    def _build_statement_prompt(self, title: str, content: str) -> str:
        return f"""
        당신은 정치인의 발언을 분석하는 데이터 전문가입니다.
        아래 뉴스를 읽고, 다음 JSON 형식으로 반환하세요.
        단 # 이 적혀있는 컬럼들은 해당 내용들을 반드시 준수하고 정보를 찾기 힘들경우 None로 반환하세요.

        {{
            "speaker": "..." # 정치인 이름,
            "party": "..." # 정당명,
            "speak_reason": "..." # 발언 이유,
            "context": "..." # 요약 내용,
            "category": "..." # 발언 카테고리 (예: "정책", "논란", "선거", "연대"),
            "type": "..." # 발언 성격 (예 : 비판, 공약, 해명, 정책제안, 논란 등)
        }}

        반드시 JSON만 반환하세요.

        제목: {title}
        내용: {content}
        """

    def _build_general_politics_prompt(self, title: str, content: str) -> str:
        return f"""
        당신은 정치 전문 기자입니다.
        아래 정치 뉴스를 2~3문장으로 요약하고, 다음 JSON 형식으로 반환하세요.
        단 # 이 적혀있는 컬럼들은 해당 내용들을 반드시 준수하고 정보를 찾기 힘들경우 None로 반환하세요.

        {{
            "ai_summary": "..." # 요약 내용,
        }}

        반드시 JSON만 반환하세요.

        제목: {title}
        내용: {content}
        """

    # ===== AI 호출 메소드 =====
    async def summarize_by_category2(self, category: str, title: str, content: str):
        try:
            prompt = self._build_prompt(category, title, content)

            # Gemini API 호출 (비동기)
            response = await asyncio.to_thread(self.model.generate_content, prompt)

            # 응답 텍스트 안전하게 추출
            raw_text = ""
            if hasattr(response, "candidates") and response.candidates:
                parts = response.candidates[0].content.parts
                if parts and hasattr(parts[0], "text"):
                    raw_text = parts[0].text.strip()

            if not raw_text:
                return {"success": False, "message": "AI 응답이 비어있음"}

            # JSON 추출 (견고)
            parsed_data = extract_json_block(raw_text)
            if parsed_data is None:
                return {"success": False, "message": "AI 응답에서 JSON 파싱 실패", "raw": raw_text}
            return {"success": True, "data": parsed_data}

        except Exception as e:
            traceback.print_exc()
            return {"success": False, "message": f"AI 요약 생성 중 오류: {str(e)}"}

    async def _generate_comprehensive_summary(self, categorized_articles: Dict[str, List[Dict[str, Any]]]) -> str:
        """카테고리별 기사 제목으로 하루 종합 요약 생성 (Gemini)."""
        try:
            category_summaries = []
            for category, articles in categorized_articles.items():
                if articles:
                    category_name = {
                        "president": "대통령 관련",
                        "parliament": "국회 관련",
                        "politics": "정치 일반",
                        "breaking": "주요 속보",
                        "government": "정부 브리핑",
                    }.get(category, category)
                    titles = [a.get("title", "") for a in articles[:5] if a.get("title")]
                    if titles:
                        category_summaries.append(f"{category_name}: " + ", ".join(titles))

            if not category_summaries:
                return "오늘은 주요 정치 뉴스가 없었습니다."

            prompt = (
                "다음은 오늘의 한국 정치 뉴스 제목들입니다. 이를 바탕으로 하루의 정치 상황을 "
                "3-4문장으로 종합 요약하세요. 가장 중요한 이슈를 우선 언급하고, 객관적·중립적인 톤으로 "
                "정치적 편향 없이 사실 중심으로 서술하세요.\n\n"
                + "\n".join(category_summaries)
            )

            response = await asyncio.to_thread(self.model.generate_content, prompt)
            text = ""
            if hasattr(response, "candidates") and response.candidates:
                parts = response.candidates[0].content.parts
                if parts and hasattr(parts[0], "text"):
                    text = parts[0].text.strip()
            return text or "요약을 생성하지 못했습니다."

        except Exception as e:
            return f"종합 요약 생성 중 오류가 발생했습니다: {str(e)}"

    async def _extract_highlights(self, articles: List[Dict[str, Any]]) -> List[str]:
        """주요 하이라이트 추출"""
        try:
            # 중요 키워드가 포함된 기사들을 우선 선별
            important_keywords = ["대통령", "국회", "법안", "정책", "선거", "개혁", "특검", "예산"]

            highlighted_articles = []
            for article in articles:
                title = article.get("title", "")
                score = sum(1 for keyword in important_keywords if keyword in title)
                if score > 0:
                    highlighted_articles.append((article, score))

            # 점수순으로 정렬하여 상위 5개 선택
            highlighted_articles.sort(key=lambda x: x[1], reverse=True)
            highlights = []

            for article, _ in highlighted_articles[:5]:
                highlights.append(f"• {article.get('title', '')}")

            return highlights if highlights else ["오늘은 특별한 정치 이슈가 없었습니다."]

        except Exception as e:
            return [f"하이라이트 추출 중 오류가 발생했습니다: {str(e)}"]

    async def get_daily_summary(self, date: str = None) -> Dict[str, Any]:
        """일일 요약 조회. 없으면 success=True + summary=None."""
        try:
            day = date or datetime.utcnow().strftime("%Y-%m-%d")
            doc = db.collection("daily_summaries").document(day).get()
            data = doc.to_dict() if doc.exists else None
            return {
                "success": True,
                "message": "조회 성공" if data else "해당 일자 요약이 아직 없습니다.",
                "data": {"summary": data},
            }
        except Exception as e:
            return {"success": False, "message": f"일일 요약 조회 오류: {str(e)}"}

    async def generate_daily_summary(self, date: str = None) -> Dict[str, Any]:
        """해당 일자 기사로 종합 요약/하이라이트 생성 후 저장."""
        try:
            day = date or datetime.utcnow().strftime("%Y-%m-%d")
            start, end = f"{day} 00:00:00", f"{day} 23:59:59"
            docs = (
                db.collection("articles")
                .where("published_at", ">=", start)
                .where("published_at", "<=", end)
                .stream()
            )
            articles = [d.to_dict() for d in docs]
            if not articles:
                # 해당 일자 기사가 없으면 최근 기사로 대체
                recent = (
                    db.collection("articles")
                    .order_by("published_at", direction=firestore.Query.DESCENDING)
                    .limit(20)
                    .stream()
                )
                articles = [d.to_dict() for d in recent]

            categorized: Dict[str, List[Dict[str, Any]]] = {}
            for a in articles:
                categorized.setdefault(a.get("category", "politics"), []).append(a)

            overview = await self._generate_comprehensive_summary(categorized)
            highlights = await self._extract_highlights(articles)

            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "id": day,
                "date": day,
                "overview": overview,
                "highlights": highlights,
                "article_count": len(articles),
                "created_at": now,
                "updated_at": now,
            }
            db.collection("daily_summaries").document(day).set(record)
            return {"success": True, "message": "일일 요약 생성 완료", "data": {"summary": record}}
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "message": f"일일 요약 생성 오류: {str(e)}"}

# AI 요약 서비스 인스턴스 생성
ai_summary_service = AISummaryService()