FROM python:3.13-slim

# Install dependencies
RUN apt update -y \
    && apt install -y \
    curl \
    ca-certificates \
    lsb-release \
    tk

# Add the PostgreSQL apt repository
RUN install -d /usr/share/postgresql-common/pgdg
RUN curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
RUN sh -c 'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
    https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > \
    /etc/apt/sources.list.d/pgdg.list'

# Install the PostgreSQL 17 client
RUN apt update -y \
    && apt install -y \
    postgresql-client-17

# Copy the deltaVic repository
COPY . /deltaVic
WORKDIR /deltaVic

# Install python requirements
RUN pip install --no-cache-dir -r requirements.txt

# Set the python stdout to be unbuffered
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "deltaVic.py"]
