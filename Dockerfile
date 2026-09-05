# ChessCouncil — 一键部署（含 Stockfish）
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY frontend ./frontend
COPY docs ./docs

ENV STOCKFISH_PATH=/usr/games/stockfish \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

VOLUME ["/app/data", "/app/logs"]

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
