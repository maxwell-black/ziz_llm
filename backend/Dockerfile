# Use a slim official Python image
FROM python:3.10-slim

# 1) Set working directory
WORKDIR /app

# 2) Copy & install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Install the Cloud SDK (for gsutil)
RUN apt-get update \
  && apt-get install -y google-cloud-sdk \
  && rm -rf /var/lib/apt/lists/*

# 4) Fetch your v2 FAISS index from GCS at build time
RUN gsutil -m cp -r gs://ziz-llm-v2-indexes/ziz_index_5-7-25 /app/faiss_index_v2

# 5) Copy the rest of your backend code
COPY . .

# 6) Launch with Gunicorn (Cloud Run will set $PORT)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
