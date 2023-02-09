FROM python:3.11.2-alpine

ENV PYTHONUNBUFFERED 1

RUN apk update && apk add rust cargo libffi-dev
RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

ADD . ./

EXPOSE 4000
CMD python app.py
