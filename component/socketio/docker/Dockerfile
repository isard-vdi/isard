# Use an official Python runtime as a parent image
FROM python:3.13-alpine

# Copy the application code
ENV PYTHONPATH /opt/isardvdi
COPY component/socketio/src /opt/isardvdi/isardvdi_socketio
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common

# Install the dependencies
COPY component/socketio/docker/requirements.txt /tmp/
RUN python3 -m venv venv
RUN venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Expose the port the app runs on
EXPOSE 5000

# uvicorn command
CMD ["venv/bin/uvicorn", "isardvdi_socketio:app", "--host", "0.0.0.0", "--port", "5000"]
