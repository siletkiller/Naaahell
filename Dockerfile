FROM python:3.11-slim

# Install system dependencies:
# - Node.js & npm (for hosted .js scripts)
# - bash (for hosted .sh scripts)
# - git, curl, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    bash \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Optimize Python execution in Docker
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=10000

WORKDIR /app

# Install dependencies in a separate layer for faster build caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files into the container
COPY . .

# Ensure storage directories and runtime log/database files exist with read/write permissions
RUN mkdir -p /app/hosted_bots /app/data && \
    touch /app/users.json /app/error.log && \
    chmod -R 777 /app/hosted_bots /app/data && \
    chmod 666 /app/users.json /app/error.log

# Render dynamically binds via the $PORT environment variable
EXPOSE 10000

# Start the bot
CMD ["python", "index.py"]