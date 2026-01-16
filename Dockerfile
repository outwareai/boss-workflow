# Boss Workflow Automation - Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port (Railway sets PORT env var)
EXPOSE 8000

# Set default port
ENV PORT=8000

# Run the application using shell to expand $PORT
CMD python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
