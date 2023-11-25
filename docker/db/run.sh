#!/bin/sh

# Start the stats recollection
if [ "$ENABLE_STATS" = "" ] || [ "$ENABLE_STATS" = "true" ]; then
	while /bin/true; do
		# List all the TCP connections that are established at the RethinkDB port
		ss -Htpn -o state established '( sport = :28015 )' | \
		    # Get only the remote IP address
		    gawk '{ print gensub(/.*\[.*:([0-9]+.*)\].*/, "\\1", "g", $4) }' | \
		    # Get the number of unique IP addresses
		    sort | uniq -c | \
		    # Print the information in Prometheus format
		    awk '{ print "rethinkdb_server_client_connections_ip{ip=\"" $2 "\"} " $1}' | \
		    # Save the result to the pertinent directory and pretty
		    sponge > /var/lib/prometheus/rethinkdb.prom.$$

		# Make the stats extraction atomic
		mv /var/lib/prometheus/rethinkdb.prom.$$ /var/lib/prometheus/rethinkdb.prom

		sleep 30

	done & # Run the loop in the background
fi

# Start RethinkDB
rethinkdb --cores 64 --bind all
