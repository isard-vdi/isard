# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY component/openapi/docker/requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt --break-system-package

COPY component/openapi/src/main.py /app/main.py
COPY pkg/oas /app/oas
COPY frontend/src/assets/img/cover-img.svg /app/cover-img.svg
COPY frontend/public/favicon.ico /app/favicon.ico

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]