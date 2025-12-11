# Use a slim Python 3.10 base image
FROM python:3.10-slim-buster

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create app directory
WORKDIR /app

# Install system dependencies (needed for some Snowflake connector dependencies)
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
# This copies app.py and cortex_chat.py (and any other files in the dir)
COPY . .

# Run the application
# We use python directly. SocketModeHandler blocks, so this keeps the container alive.
CMD ["python", "app.py"]