FROM python:3.12-slim
WORKDIR /app
COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /app/deploy/requirements.txt
COPY baton /app/baton
COPY server /app/server
COPY fixtures /app/fixtures
COPY third_party /app/third_party
COPY web /app/web
ENV PYTHONUNBUFFERED=1 BATON_DATA=/data
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
