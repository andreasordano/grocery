FROM python:3.12-slim

WORKDIR /app

# system deps for some python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY ../requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY .. /app

ENV PYTHONUNBUFFERED=1
COPY ../scripts /app/scripts
RUN chmod +x /app/scripts/wait-for-db.sh || true

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/scripts/wait-for-db.sh"]
CMD ["uvicorn", "api.service:app", "--host", "0.0.0.0", "--port", "8000"]
