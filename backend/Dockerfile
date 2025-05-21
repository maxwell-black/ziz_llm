FROM python:3.10-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ← replace your old “install google-cloud-sdk” with this block:
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      apt-transport-https ca-certificates gnupg && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
      | tee /usr/share/keyrings/cloud.google.gpg > /dev/null && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] \
      https://packages.cloud.google.com/apt cloud-sdk main" \
      > /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-cloud-sdk && \
    rm -rf /var/lib/apt/lists/*

RUN gsutil -m cp -r gs://ziz-llm-v2-indexes/ziz_index_5-7-25 /app/faiss_index_v2

COPY . .
CMD ["gunicorn","--bind","0.0.0.0:8080","main:app"]

