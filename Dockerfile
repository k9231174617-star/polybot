FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1         PYTHONUNBUFFERED=1         PYTHONPATH=/app/polybot

WORKDIR /app/polybot

COPY polybot/bot/requirements.txt /app/polybot/bot/requirements.txt
RUN pip install --no-cache-dir -r /app/polybot/bot/requirements.txt

COPY polybot /app/polybot

CMD ["python", "-m", "bot.main"]
