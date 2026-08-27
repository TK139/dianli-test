FROM python:3.11-slim

# 设置环境变量，避免交互式安装和字节码缓存
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .

# 使用阿里云 PyPI 镜像源安装依赖
RUN pip install -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com

# 复制项目代码
COPY . .

EXPOSE 8501

# 健康检查（可选但推荐）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]