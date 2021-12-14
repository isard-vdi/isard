FROM rethinkdb

RUN apt-get update && \
    apt-get install -y \
    python3-pip && \
    apt-get clean autoclean && \
    apt-get autoremove --yes && \
    rm -rf \
    	/var/lib/apt \
        /var/lib/dpkg \
        /var/lib/cache \
        /var/lib/log
RUN pip3 install --no-cache-dir \
    rethinkdb
HEALTHCHECK --interval=15s CMD echo "r.db('rethinkdb').table('current_issues').count().eq(0).run() and exit(0) or exit(1)" | rethinkdb repl
