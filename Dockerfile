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
RUN pip install --no-cache-dir llama-index-llms-openai
COPY connect_drive.py parse_tika.py parse_unstructured.py parse_docling.py chunk.py enrich.py ./

CMD ["sh", "-c", "python parse_tika.py && python parse_unstructured.py && python parse_docling.py && python chunk.py && python enrich.py"]
