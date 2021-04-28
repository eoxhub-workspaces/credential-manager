FROM python:3.9.4

ENV PROMETHEUS_MULTIPROC_DIR /var/tmp/prometheus_multiproc_dir
RUN mkdir $PROMETHEUS_MULTIPROC_DIR \
    && chown www-data $PROMETHEUS_MULTIPROC_DIR \
    && chmod g+w $PROMETHEUS_MULTIPROC_DIR

RUN apt-get update && apt-get install tini

WORKDIR /srv/service
ADD requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ADD . .

USER www-data


CMD ["gunicorn", "--bind=0.0.0.0:8080", "--config", "gunicorn.conf.py", "--workers=1", "-k", "uvicorn.workers.UvicornWorker", "--log-level=INFO", "my_secrets:app"]
