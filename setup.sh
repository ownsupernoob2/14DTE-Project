#!/bin/bash

# Smart Mirror Project - Quick Start Script

echo "🚀 Smart Mirror Project - Quick Start"
echo "======================================="
echo ""

# Check if Node is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 16+"
    exit 1
fi

# Check if Go is installed
if ! command -v go &> /dev/null; then
    echo "❌ Go is not installed. Please install Go 1.21+"
    exit 1
fi

echo "✅ Node.js version: $(node --version)"
echo "✅ Go version: $(go version)"
echo ""

# Frontend setup
echo "📦 Setting up frontend..."
cd web
npm install
echo "✅ Frontend dependencies installed"
echo ""

# Backend setup
echo "📦 Setting up backend..."
cd ../server
go mod download
go mod tidy
echo "✅ Backend dependencies installed"
echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit server/.env with your Auth0 credentials"
    echo ""
fi

echo "======================================="
echo "✅ Setup complete!"
echo ""
echo "To start development:"
echo ""
echo "Frontend:"
echo "  cd web"
echo "  npm run dev"
echo ""
echo "Backend:"
echo "  cd server"
echo "  go run ."
echo ""
echo "Or use Docker:"
echo "  cd server"
echo "  docker-compose up --build"
echo ""
echo "Visit http://localhost:5173 for the frontend"
echo "API will be at http://localhost:8080"
