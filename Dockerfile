# Dockerfile

FROM python:3.11-slim
WORKDIR /app
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы проекта
COPY bot.py .
# Обновлено, чтобы копировать из папки 'data' (если вы ее создали)
COPY data/channel_signatures.db channel_signatures.db

CMD ["python", "bot.py"]
