# Floodlight Controller on Alpine Linux Container
#
# This file inspired by https://floodlight.atlassian.net/wiki/spaces/floodlightcontroller/pages/1343544/Installation+Guide
#
# Build image using this Dockerfile
#    docker build -t haidarns/floodlight .
#
# Run container using this image:
#   docker run -it -p 6653:6653 -p 8080:8080 haidarns/floodlight

#FROM openjdk:8-jdk-alpine
FROM openjdk:alpine
LABEL maintainer="haidar.ns@gmail.com"

# Uncomment commented line below if you want create slim floodlight image size, then add '&& \' after 'chmod 777 /var/lib/floodlight'
RUN apk --update --no-cache add build-base apache-ant maven python-dev git && \
git clone -b v1.2 https://github.com/floodlight/floodlight.git && \
cd floodlight/ && git submodule init && git submodule update && \
ant && mkdir /var/lib/floodlight && chmod 777 /var/lib/floodlight && \
apk --no-cache del build-base apache-ant maven git python-dev && \
mkdir /home/floodlight/ && cp target/floodlight.jar /home/floodlight/ && \
cp -r src/ /home/floodlight/ && cd /home && rm -rf /floodlight

WORKDIR /home/floodlight

EXPOSE 6653 8080

CMD java -jar /home/floodlight/floodlight.jar
