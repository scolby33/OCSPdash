FROM python:3.6.5

RUN pip install --upgrade pip
RUN pip install pipenv gunicorn psycopg2

COPY Pipfile.lock /
RUN set -ex && pipenv install --deploy --system

COPY . /app
WORKDIR /app
RUN set -ex && pip install -e .

