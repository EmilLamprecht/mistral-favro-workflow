FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "mistralai-workflows>=3.10" httpx

COPY . .

CMD ["python", "worker.py"]
