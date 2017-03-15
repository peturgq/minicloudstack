FROM python:2.7-slim

WORKDIR /build
ADD requirements.txt /build

RUN pip install -r requirements.txt

WORKDIR /install
ADD / /install
RUN pip install -e .

