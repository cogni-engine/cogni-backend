FROM python:3.13
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN apt-get update && apt-get install -y build-essential g++
RUN pip install --upgrade pip && pip install poetry 
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

COPY . .

EXPOSE 8000



