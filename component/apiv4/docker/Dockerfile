# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# System packages: fonts-liberation is needed by gen_image.py to generate
# placeholder desktop card images via PIL.ImageFont.truetype().
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-liberation openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY component/apiv4/docker/requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt --break-system-package

# Copy the rest of the application code
COPY component/apiv4/src .

# Import isardvdi_common package
ENV PYTHONPATH /opt/isardvdi:/opt/isardvdi/isardvdi_protobuf
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf

# Default logo fallback (same asset used by isard-static)
COPY component/frontend/src/assets/logo.svg /usr/share/nginx/html/default_logo.svg

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]