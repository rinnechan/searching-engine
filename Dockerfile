# 1. Use Python 3.11 (More stable wheels than 3.9)
FROM python:3.11-slim

# 2. Prevent Python from buffering stdout (Logs show up faster)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 3. CRITICAL FIX: Install build tools and libraries needed for LlamaIndex
# 'build-essential' provides gcc for compiling python packages
# 'libmagic1' is required for file type detection in LlamaParse
RUN apt-get update && apt-get install -y \
    build-essential \
    libmagic1 \
    libmagic-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy requirements (Ensure this filename matches what is on your disk!)
# I changed it to plural 'requirements.txt' as that is standard.
# CHECK: Rename your local file to 'requirements.txt' if it is 'requirement.txt'
COPY requirements.txt .

# 5. Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the code
COPY . .

# 7. Default command
CMD ["python", "src/main.py", "--help"]