FROM python:3.6.2

RUN mkdir -p /usr/src/app

COPY . /usr/src/app
WORKDIR /usr/src/app

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn psycopg2
RUN pip install .

# This is the stuff that should go in Docker-compose after
# EXPOSE 8000
# CMD ["gunicorn", "-b", "0.0.0.0:8000", "ocspdash.web.run:app"]
