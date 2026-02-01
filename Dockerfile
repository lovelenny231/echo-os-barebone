# ECHO OS Barebone - Docker Container
FROM python:3.11-slim

# Working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY src/ ./src/
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY data/ ./data/

# Environment variables
ENV RAG_BACKEND=bundled
ENV RAG_DATA_DIR=/app/data
ENV PYTHONPATH=/app
ENV PORT=8000

# UTF-8 locale
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

# Disable Python output buffering
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Start FastAPI application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
