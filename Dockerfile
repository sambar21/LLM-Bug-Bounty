FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY triage ./triage
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .

# Pass the key at run time: docker run --env-file .env -v "$PWD/results:/app/results" ...
CMD ["make", "bench"]
