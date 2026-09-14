FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/warcs /app/data

ENV PYTHONUNBUFFERED=1
ENV WARCS_DIR=/app/warcs
ENV DATA_DIR=/app/data

ENTRYPOINT ["python", "main.py"]
CMD ["worker"]
