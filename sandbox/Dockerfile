FROM python:3.13-slim

RUN pip install --no-cache-dir pandas==3.0.6 pyarrow==25.0.1 \
    && useradd --uid 10001 --no-create-home sandbox

USER 10001
