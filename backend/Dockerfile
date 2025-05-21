# Use Google’s slim Cloud SDK image so we get gsutil for free
FROM google/cloud-sdk:slim

# Install Python 3 and pip
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Copy & install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 2) Pull your v2 FAISS index from GCS
RUN gsutil -m cp -r gs://ziz-llm-v2-indexes/ziz_index_5-7-25 /app/faiss_index_v2

# 3) Copy in your application code
COPY . .

# 4) Start the Flask/Gunicorn server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
