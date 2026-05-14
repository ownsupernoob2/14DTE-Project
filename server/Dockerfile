# Build stage
FROM golang:1.21-alpine AS builder

WORKDIR /app

# Install dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o smart-mirror-api .

# Final stage
FROM alpine:latest

WORKDIR /root/

# Install ca-certificates for HTTPS, along with Python
RUN apk --no-cache add ca-certificates python3 py3-pip

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Copy binary from builder
COPY --from=builder /app/smart-mirror-api .

# Copy python scripts
COPY *.py ./

# Expose port
EXPOSE 8080

# Run the application
CMD ["./smart-mirror-api"]
