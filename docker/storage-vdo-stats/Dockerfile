FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf

# device-mapper carries dmsetup: the VDO fill is the only thing that needs it.
RUN apk add --no-cache device-mapper py3-redis python3

# Two pure-stdlib modules, so the common package and its deps stay out.
RUN mkdir -p /opt/isardvdi/isardvdi_common/connections \
             /opt/isardvdi/isardvdi_common/lib/storage \
    && touch /opt/isardvdi/isardvdi_common/__init__.py \
             /opt/isardvdi/isardvdi_common/connections/__init__.py \
             /opt/isardvdi/isardvdi_common/lib/__init__.py \
             /opt/isardvdi/isardvdi_common/lib/storage/__init__.py
COPY component/_common/src/isardvdi_common/connections/redis_urls.py /opt/isardvdi/isardvdi_common/connections/redis_urls.py
COPY component/_common/src/isardvdi_common/lib/storage/physical_usage.py /opt/isardvdi/isardvdi_common/lib/storage/physical_usage.py
COPY docker/storage/utils/storage-pool-physical /usr/local/bin/storage-pool-physical

ENV PYTHONPATH=/opt/isardvdi PYTHONUNBUFFERED=1
CMD ["/usr/local/bin/storage-pool-physical"]
