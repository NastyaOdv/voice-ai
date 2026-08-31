FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

# Queue worker — no HTTP port.
ENTRYPOINT ["sh", "./entrypoint.sh"]
