FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create persistent volume directory for session file
RUN mkdir -p /data

CMD ["python", "bot_render.py"]
