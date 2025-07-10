"""
합법적 크롤링을 위한 유틸리티
"""
import requests
import time
from urllib.robotparser import RobotFileParser
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class LegalCrawler:
    def __init__(self, user_agent: str = "PoliticalNewsBot/1.0"):
        self.user_agent = user_agent
        self.rate_limits: Dict[str, float] = {}
        self.last_requests: Dict[str, float] = {}

    def check_robots_txt(self, url: str) -> bool:
        """robots.txt 확인"""
        try:
            from urllib.parse import urljoin, urlparse

            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            robots_url = urljoin(base_url, '/robots.txt')

            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()

            return rp.can_fetch(self.user_agent, url)

        except Exception as e:
            logger.warning(f"robots.txt 확인 실패: {e}")
            return True  # 확인 불가 시 허용으로 간주

    def respect_rate_limit(self, domain: str, min_delay: float = 1.0):
        """레이트 리미트 준수"""
        current_time = time.time()

        if domain in self.last_requests:
            time_since_last = current_time - self.last_requests[domain]
            if time_since_last < min_delay:
                sleep_time = min_delay - time_since_last
                logger.info(f"{domain}에 대해 {sleep_time:.2f}초 대기")
                time.sleep(sleep_time)

        self.last_requests[domain] = time.time()

    def safe_request(self, url: str, **kwargs) -> Optional[requests.Response]:
        """안전한 HTTP 요청"""
        try:
            from urllib.parse import urlparse

            # robots.txt 확인
            if not self.check_robots_txt(url):
                logger.warning(f"robots.txt에 의해 접근 금지: {url}")
                return None

            # 레이트 리미트 적용
            domain = urlparse(url).netloc
            self.respect_rate_limit(domain)

            # 요청 헤더 설정
            headers = kwargs.get('headers', {})
            headers.update({
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            kwargs['headers'] = headers

            # 타임아웃 설정
            kwargs.setdefault('timeout', 10)

            response = requests.get(url, **kwargs)
            response.raise_for_status()

            return response

        except Exception as e:
            logger.error(f"요청 실패 {url}: {e}")
            return None

# 전역 인스턴스
legal_crawler = LegalCrawler()