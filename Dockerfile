# EncloSURE web page: docker build -t enclosure . && docker run -p 8000:8000 enclosure
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxrender1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY enclosure ./enclosure
RUN pip install --no-cache-dir ".[web]"
EXPOSE 8000
# Hosts such as Render set PORT.
CMD ["sh", "-c", "uvicorn enclosure.web:app --host 0.0.0.0 --port ${PORT:-8000}"]
