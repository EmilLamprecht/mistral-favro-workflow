FROM python:3.12-slim
RUN pip install --no-cache-dir "mistralai-workflows>=3.10" httpx
CMD ["sleep", "infinity"]
