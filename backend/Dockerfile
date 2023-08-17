FROM python:3.11.1-slim-bullseye

WORKDIR /build

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.txt requirements.txt

# Install system dependencies
RUN pip install -r requirements.txt

# Copy the rest of app
COPY .env .env
COPY main.py main.py

# touch db.json
RUN touch db.json
RUN mkdir audio_files

# Create new user to run app process as unprivilaged user
CMD ["python", "main.py"]