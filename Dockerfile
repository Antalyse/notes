# Use an official lightweight Python base image.
FROM python:3.11-slim

# Set the work directory.
WORKDIR /app

# Install dependencies.

RUN pip install flask flask_migrate flask_sqlalchemy flask_login psycopg2-binary werkzeug

# Copy the project.
COPY . /app/

# Expose port (Flask default).
EXPOSE 5000

# Run the application.
CMD ["python", "app.py"]
