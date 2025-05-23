# ~/ziz_llm/Dockerfile
# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables for Python and the working directory
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME

# Install system dependencies if any are needed in the future (none for now)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Copy backend requirements first to leverage Docker cache
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend application code and the FAISS index
# This includes main.py and the faiss_index subdirectory
COPY backend/ ./

# Copy the built React frontend files into the expected directory (/app/react_build)
COPY frontend/build ./react_build/

# Define the command to run the application using Gunicorn when the container starts
# Cloud Run injects the PORT environment variable. Gunicorn binds to all interfaces (0.0.0.0).
# Increase workers/threads/timeout as needed based on expected load and Cloud Run instance size.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app