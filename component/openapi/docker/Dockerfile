FROM alpine:3.22.0

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip

WORKDIR /app

COPY component/openapi/docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY component/openapi/src/main.py /app/main.py
COPY pkg/oas /app/oas
COPY frontend/src/assets/img/cover-img.svg /app/cover-img.svg
COPY frontend/public/favicon.ico /app/favicon.ico

EXPOSE 5000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]