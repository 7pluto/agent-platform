FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" fastapi uvicorn[standard] pydantic pydantic-settings httpx cryptography redis sqlalchemy[asyncio] asyncpg alembic langgraph minio pypdf python-docx pgvector python-multipart
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

ENV AGENT_APP_ENV=prod
ENV AGENT_IAM_MODE=ruoyi
ENV AGENT_STORAGE_MODE=postgres
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
