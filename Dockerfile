# EncloSURE web page, with draftwright for drawings.
#   docker build -t enclosure . && docker run -p 8000:8000 enclosure

# 1. draftwright (ASME fork), built from its repository at a fixed commit.
FROM rust:1-bookworm AS draftwright
ARG DRAFTWRIGHT_REPO=https://github.com/ethanmarshall/draftwright-rust
ARG DRAFTWRIGHT_REF=369c74609ea12434f1c4de03a02537b2dd181d40
RUN git clone --filter=blob:none "$DRAFTWRIGHT_REPO" /src \
    && cd /src && git checkout "$DRAFTWRIGHT_REF" \
    && cargo build --release --bin draftwright \
    && cp target/release/draftwright /draftwright && rm -rf /src/target

# 2. The web page.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxrender1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=draftwright /draftwright /usr/local/bin/draftwright
ENV DRAFTWRIGHT=/usr/local/bin/draftwright
WORKDIR /app
COPY pyproject.toml README.md ./
COPY enclosure ./enclosure
RUN pip install --no-cache-dir ".[web]"
EXPOSE 8000
# Hosts such as Render set PORT.
CMD ["sh", "-c", "uvicorn enclosure.web:app --host 0.0.0.0 --port ${PORT:-8000}"]
