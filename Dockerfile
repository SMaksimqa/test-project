FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY newsbot ./newsbot

# Слушатель «новости» по запросу (long-polling, работает 24/7).
# Утренний дайджест по расписанию отправляет GitHub Actions отдельно.
CMD ["python", "-m", "newsbot.listen"]
