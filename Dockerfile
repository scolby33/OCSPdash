FROM python:3.6.2-jessie

RUN pip install pymysql gunicorn psycopg2

ADD requirements.txt /
RUN pip install -r requirements.txt

COPY . /app
WORKDIR /app

RUN pip install .
