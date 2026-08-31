FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# espeak-ng provides the phonemizer backend Piper uses.
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Piper English voice (lessac, medium ~63MB). Baked into the image so startup is
# deterministic and offline. Model + its JSON config must sit side by side.
ADD https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx /app/voices/en_US-lessac-medium.onnx
ADD https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json /app/voices/en_US-lessac-medium.onnx.json

COPY . .
RUN pip install --no-cache-dir .

# Queue worker — no HTTP port.
ENTRYPOINT ["sh", "./entrypoint.sh"]
