############ FastAPI #############

# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container to /app
WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt

# Add the current directory contents into the container at /app
ADD . /app

# Copy .env.example to .env
COPY .env.example .env

# Make port 80 available to the world outside this container
EXPOSE 80

# Define environment variable

ENV NAME World

# Run the command to start Uvicorn
CMD ["uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "5001"]
