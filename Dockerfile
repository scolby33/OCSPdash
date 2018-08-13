FROM python:3.7.0

RUN pip install --upgrade pip setuptools wheel
RUN pip install gunicorn psycopg2

COPY . /app
WORKDIR /app
RUN set -ex && pip install -r requirements.txt
RUN set -ex && pip install -e .

