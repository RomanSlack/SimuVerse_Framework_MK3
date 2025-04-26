FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY memory_system/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY memory_system/ /app/memory_system/

# Environment variables
ENV PYTHONPATH=/app
ENV QDRANT_URL=http://qdrant
ENV QDRANT_PORT=6333

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]