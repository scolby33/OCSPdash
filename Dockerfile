FROM python:3.6.2

RUN mkdir -p /usr/src/app

COPY . /usr/src/app
WORKDIR /usr/src/app

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn
RUN pip install .

EXPOSE 8000

# This works, and doesn't need GUnicorn
# CMD ["python3", "-m", "ocspdash", "web"]

CMD ["gunicorn", "-b", "0.0.0.0:8000", "ocspdash.web.run:app"]
