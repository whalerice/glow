FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sql ./sql
COPY app ./app
COPY templates ./templates

ENTRYPOINT ["python", "-m", "app"]
