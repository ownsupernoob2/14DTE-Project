# ----------------------------------------------------
# Stage 1: Build the Go Server
# ----------------------------------------------------
FROM golang:latest AS builder

ENV GOTOOLCHAIN=auto

WORKDIR /app

# Cache Go modules
COPY go.mod go.sum ./
RUN go mod download

# Copy Go code and build static binary
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o smart-mirror-api .

# ----------------------------------------------------
# Stage 2: Runtime Image with Python & Face Recognition
# ----------------------------------------------------
FROM python:3.11-slim-bookworm

WORKDIR /root

# Install essential dependencies for dlib / face_recognition and certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y build-essential cmake \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /root/.cache

# Copy compiled Go binary
COPY --from=builder /app/smart-mirror-api .

# Copy Python helper scripts
COPY *.py ./

# Create default directories for data persistence
RUN mkdir -p data encodings faces temp

EXPOSE 8080

CMD ["./smart-mirror-api"]
