FROM nicolargo/glances:3.2.4-full

COPY docker/glances/glances.conf /glances/conf/glances.conf.template
COPY docker/glances/run.sh /run.sh

CMD  [ "/run.sh" ]
