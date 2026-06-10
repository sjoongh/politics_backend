FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY . .

# Cloud Run은 $PORT(기본 8080)로 리슨해야 함. run_server.py가 os.getenv("PORT")를 사용.
ENV PORT=8080
EXPOSE 8080

CMD ["python", "run_server.py"]
