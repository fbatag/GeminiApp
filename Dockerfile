FROM python:3.9-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables (optional)
ENV FLASK_APP=main.py
ENV FLASK_RUN_HOST=0.0.0.0

# Expose the port Flask is running on
EXPOSE 8080

# Start the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 20 --timeout 0 main:app
