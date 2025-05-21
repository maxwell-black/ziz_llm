# 1) Use slim official Python base
FROM python:3.10-slim

# 2) Create and activate a venv so pip can install non-Debian packages
WORKDIR /app
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# 3) Install your Python deps inside the venv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Install curl & add Google Cloud SDK apt repo, then install gsutil
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      apt-transport-https ca-certificates gnupg curl \
 && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
      | apt-key add - \
 && echo "deb https://packages.cloud.google.com/apt cloud-sdk main" \
      > /etc/apt/sources.list.d/google-cloud-sdk.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends google-cloud-sdk \
 && rm -rf /var/lib/apt/lists/*

# 5) Fetch your v2 FAISS index from GCS into the image
RUN gsutil -m cp -r gs://ziz-llm-v2-indexes/ziz_index_5-7-25 /app/faiss_index_v2

# 6) Copy in the rest of your backend code
COPY . .

# 7) Launch via Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
