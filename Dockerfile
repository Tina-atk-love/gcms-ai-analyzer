FROM python:3.12-slim

LABEL maintainer="gcms-ai-analyzer"
LABEL description="GC-MS AI Analyzer — Open-source NIST alternative for flavor/compound analysis"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# App code
COPY *.py .
COPY spectral_library.py public_library_manager.py flavor_tools.py ./
COPY public_libraries/ ./public_libraries/

# Output dir
RUN mkdir -p /data /app/output/agent_results/plots

EXPOSE 8501

ENV PYTHONUNBUFFERED=1
ENV DEEPSEEK_API_KEY=""

VOLUME ["/data", "/app/output"]

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
