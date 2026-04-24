# Use an official Python runtime as a parent image
FROM python:3.13-alpine

# Copy the application code
ENV PYTHONPATH /opt/isardvdi:/opt/isardvdi/isardvdi_protobuf:/opt/isardvdi/asyncapi_changefeed
COPY component/change-handler/src /opt/isardvdi/isardvdi_change-handler
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf
COPY pkg/gen/asyncapi/changefeed /opt/isardvdi/asyncapi_changefeed

# Install the dependencies
COPY component/change-handler/docker/requirements.txt /tmp/
RUN python3 -m venv venv
RUN venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Start command
CMD ["venv/bin/python", "-m", "isardvdi_change-handler"]
STOPSIGNAL SIGTERM
