FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY bot/ bot/
COPY config.toml .

RUN pip install --no-cache-dir .

CMD ["python", "-m", "bot.main"]
