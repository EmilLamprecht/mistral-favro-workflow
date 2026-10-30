FROM python:3.12-slim

# Secrets are injected as build args; declare them (unused at build time).
ARG POSTHOG_API_KEY

WORKDIR /app

RUN pip install --no-cache-dir "mistralai-workflows>=3.10" httpx

COPY . .

CMD ["python", "worker.py"]
