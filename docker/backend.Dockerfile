# 백엔드 (FastAPI) + 적재기. 컨텍스트 = 저장소 루트.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1

# 의존성 먼저 (레이어 캐시)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

# 앱 + 적재기 (ingest 는 app 패키지를 sys.path 로 참조)
COPY backend /app/backend
COPY ingest /app/ingest

# SQLite 데이터(영속 볼륨)
ENV DB_PATH=/app/data/app.sqlite
RUN mkdir -p /app/data
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
