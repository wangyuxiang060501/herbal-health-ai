# ============================================================================
# 后端镜像（FastAPI + LangGraph + RAG）
#
# 构建（在仓库根目录）：
#   docker build -f backend/Dockerfile -t herb-backend:latest ./backend
# 运行：
#   docker run --rm -p 8000:8000 -e LLM_PROVIDER=mock herb-backend:latest
# ============================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖先行：单独一层，改代码不会触发重装依赖
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install "uvicorn[standard]>=0.30,<1.0"

COPY . .

# 知识库切片与索引在**构建期**生成，避免每个容器启动时重复算一遍
# （734 片切片的向量化约需数秒到数十秒，取决于 embedder 档位）
RUN python scripts/build_kb.py || echo "[WARN] 知识库构建失败，启动时会降级为结构化检索"

# 运行时数据（SQLite / Chroma / 索引）挂到卷上，避免容器重建即丢数据
VOLUME ["/app/var"]

EXPOSE 8000

# 健康检查直接复用 /health，不要另写 curl（slim 镜像里没有）
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
