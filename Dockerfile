FROM python:3.11-slim

# Prevent Python from writing pyc files & buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install git for git+https dependencies
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Configure git to use https instead of ssh (no auth needed for public repos)
RUN git config --global url."https://github.com/".insteadOf git://github.com/

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Start the bot
CMD ["python", "-m", "bot.main"]