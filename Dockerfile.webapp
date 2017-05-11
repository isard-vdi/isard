FROM python:3.5-slim
MAINTAINER isard <info@isard.com>

ENV INSTALL_PATH /isard
RUN mkdir -p $INSTALL_PATH
WORKDIR $INSTALL_PATH

COPY ./install/docker/requirements.pip3 requirements.pip3
RUN pip3 install -r requirements.pip3
COPY . .
COPY ./install/docker/isard.conf ./isard.conf
RUN tar xvf install/docker/bower_components.tar.gz -C webapp/
CMD python3 /isard/run_webapp.py
