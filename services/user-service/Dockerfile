FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy source and install the service with its dependencies.
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000

# entrypoint runs `alembic upgrade head` then starts uvicorn.
ENTRYPOINT ["sh", "./entrypoint.sh"]
