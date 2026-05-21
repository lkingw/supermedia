FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY task_manager.py .

RUN mkdir -p /app/data

CMD ["python", "-u", "task_manager.py"]
