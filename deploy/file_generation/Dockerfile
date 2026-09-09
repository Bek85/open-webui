FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-dejavu-extra \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY renderer.py service.py ./
RUN mkdir /data && chown 10001:10001 /data
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=2)"
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8081", "--no-access-log", "--limit-concurrency", "16"]

FROM runtime AS test
USER root
RUN pip install --no-cache-dir httpx==0.28.1
COPY tests /app/tests
USER 10001:10001
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
