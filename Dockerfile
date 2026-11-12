FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
ENV CACHE_FILE=/data/item_cache.json PYTHONUNBUFFERED=1
VOLUME /data
CMD ["python", "bot.py"]
