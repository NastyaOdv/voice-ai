FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy source and install the service with its dependencies.
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000

# entrypoint: run migrations -> start uvicorn. JWT keys come from env (JWT_PRIVATE_KEY).
ENTRYPOINT ["sh", "./entrypoint.sh"]
