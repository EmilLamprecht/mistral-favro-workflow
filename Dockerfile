FROM python:3.12-slim

# Secrets are injected as build args; declare them (unused at build time).
ARG FAVRO_USER_EMAIL
ARG FAVRO_API_TOKEN
ARG FAVRO_ORG_ID

WORKDIR /app

RUN pip install --no-cache-dir "mistralai-workflows>=3.10" httpx

COPY . .

CMD ["python", "worker.py"]
