# Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project into image
COPY . .

# Expose health port
EXPOSE 8080

# Run the main entrypoint
CMD ["python", "main.py"]