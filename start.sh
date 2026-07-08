#!/bin/bash
# GC-MS AI Analyzer — One-Command Startup
# ========================================
# Usage:
#   ./start.sh                    → local Streamlit
#   ./start.sh docker             → Docker
#   ./start.sh docker --build     → Docker (rebuild image)

MODE=${1:-local}

if [ "$MODE" = "docker" ]; then
    echo "🐳 Starting with Docker..."
    if [ "$2" = "--build" ]; then
        docker-compose build --no-cache
    fi
    docker-compose up -d
    echo ""
    echo "✅ GC-MS AI Analyzer running at: http://localhost:8501"
    echo "   Data directory: ./data (mount your .D folders here)"
    echo "   Output: ./output"
    echo ""
    echo "   Stop: docker-compose down"
else
    echo "🧬 Starting GC-MS AI Analyzer locally..."
    echo ""

    # Check Python
    if ! command -v python &> /dev/null; then
        echo "❌ Python not found. Install Python 3.10+ first."
        exit 1
    fi

    # Check deps
    python -c "import streamlit" 2>/dev/null || {
        echo "📦 Installing dependencies..."
        pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    }

    # Set API key if not set
    if [ -z "$DEEPSEEK_API_KEY" ]; then
        echo ""
        echo "⚠️  DEEPSEEK_API_KEY not set."
        echo "   Get one at: https://platform.deepseek.com"
        echo "   Then: export DEEPSEEK_API_KEY='sk-xxx'"
        echo "   Or enter it in the web UI sidebar."
        echo ""
    fi

    streamlit run app.py --server.port=8501
fi
