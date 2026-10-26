FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# shortcut: CPU torch, this image has no GPU. Switch the index when the host has one.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --force-reinstall --no-deps torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir llama-index-llms-openai psycopg[binary]
COPY ramonda ./ramonda

CMD ["python", "-m", "ramonda.ingestion"]
