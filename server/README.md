# Smart Mirror API

This is the backend API for the Smart Mirror application, built with Go and Echo.

## Setup

### Prerequisites
- Go 1.21 or higher
- Auth0 account

### Environment Variables

Create a `.env` file in the server directory:

```
AUTH0_DOMAIN=your-auth0-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=your-api-audience
PORT=8080
DATABASE_URL=your-database-url
```

### Installation

```bash
# Install dependencies
go mod download
go mod tidy

# Run the server
go run main.go auth.go

# Or build
go build -o smart-mirror-api
./smart-mirror-api
```

## API Endpoints

### Authentication
- `POST /auth/login` - Login with email and password
- `POST /auth/register` - Register a new user
- `POST /auth/refresh` - Refresh JWT token

### User (Protected)
- `GET /api/users/me` - Get current user
- `GET /api/users/:id` - Get user by ID
- `PUT /api/users/:id` - Update user

### Dashboard & Widgets (Protected)
- `GET /api/dashboard` - Get user's dashboard
- `GET /api/dashboard/widgets` - Get all widgets
- `POST /api/dashboard/widgets` - Create widget
- `PUT /api/dashboard/widgets/:id` - Update widget
- `DELETE /api/dashboard/widgets/:id` - Delete widget

### Health
- `GET /health` - Health check endpoint

## Architecture

- `main.go` - Main application, routes, and basic handlers
- `auth.go` - Auth0 integration and authentication logic

## Next Steps

- [ ] Implement database layer (PostgreSQL/MongoDB)
- [ ] Complete Auth0 integration
- [ ] Add input validation
- [ ] Add error handling middleware
- [ ] Add logging
- [ ] Add tests
- [ ] Deploy to production
