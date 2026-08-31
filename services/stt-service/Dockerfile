FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# libgomp1 is needed by CTranslate2 (faster-whisper's backend).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

# Queue worker — no HTTP port.
ENTRYPOINT ["sh", "./entrypoint.sh"]
