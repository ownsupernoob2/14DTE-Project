# Smart Mirror API Documentation

## Base URL
```
http://localhost:8080
```

## Authentication
All protected endpoints require a valid JWT token in the Authorization header:
```
Authorization: Bearer <jwt_token>
```

## Response Format
All endpoints return JSON responses with the following structure:

### Success Response
```json
{
  "data": { /* response data */ },
  "message": "Optional message",
  "timestamp": "2024-04-24T12:00:00Z"
}
```

### Error Response
```json
{
  "error": "Error 400",
  "message": "Description of error",
  "code": 400
}
```

---

## Endpoints

### Health Check
Check if the API is running.

```http
GET /health
```

**Response:**
```json
{
  "status": "ok"
}
```

---

## Authentication Endpoints

### Login
Authenticate user and get JWT token.

```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response:** `200 OK`
```json
{
  "data": {
    "token": "eyJhbGc...",
    "expires_in": 3600
  }
}
```

**Errors:**
- `401 Unauthorized` - Invalid credentials
- `400 Bad Request` - Missing required fields

---

### Register
Create a new user account.

```http
POST /auth/register
Content-Type: application/json

{
  "email": "newuser@example.com",
  "password": "password123",
  "name": "John Doe"
}
```

**Response:** `201 Created`
```json
{
  "data": {
    "id": "user-123",
    "email": "newuser@example.com",
    "name": "John Doe"
  }
}
```

**Errors:**
- `400 Bad Request` - Invalid input or user already exists
- `422 Unprocessable Entity` - Password too weak

---

### Refresh Token
Get a new JWT token using refresh token.

```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "previous_refresh_token"
}
```

**Response:** `200 OK`
```json
{
  "data": {
    "token": "eyJhbGc...",
    "refresh_token": "new_refresh_token",
    "expires_in": 3600
  }
}
```

---

## User Endpoints (Protected)

### Get Current User
Get information about the authenticated user.

```http
GET /api/users/me
Authorization: Bearer <jwt_token>
```

**Response:** `200 OK`
```json
{
  "data": {
    "id": "user-123",
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

---

### Get User by ID
Get information about a specific user.

```http
GET /api/users/:id
Authorization: Bearer <jwt_token>
```

**Response:** `200 OK`
```json
{
  "data": {
    "id": "user-123",
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

---

### Update User
Update user profile information.

```http
PUT /api/users/:id
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "name": "Jane Doe",
  "email": "newemail@example.com"
}
```

**Response:** `200 OK`
```json
{
  "data": {
    "id": "user-123",
    "email": "newemail@example.com",
    "name": "Jane Doe"
  }
}
```

---

## Dashboard Endpoints (Protected)

### Get Dashboard
Get the user's dashboard with all widgets.

```http
GET /api/dashboard
Authorization: Bearer <jwt_token>
```

**Response:** `200 OK`
```json
{
  "data": {
    "id": "dashboard-123",
    "user_id": "user-123",
    "widgets": [
      {
        "id": "widget-1",
        "type": "clock",
        "x": 100,
        "y": 150,
        "data": {}
      }
    ]
  }
}
```

---

### Get All Widgets
Get all widgets for the current user's dashboard.

```http
GET /api/dashboard/widgets
Authorization: Bearer <jwt_token>
```

**Response:** `200 OK`
```json
{
  "data": [
    {
      "id": "widget-1",
      "type": "clock",
      "x": 100,
      "y": 150
    },
    {
      "id": "widget-2",
      "type": "weather",
      "x": 350,
      "y": 200
    }
  ]
}
```

---

### Create Widget
Add a new widget to the dashboard.

```http
POST /api/dashboard/widgets
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "type": "clock",
  "x": 100,
  "y": 150,
  "data": {}
}
```

**Widget Types:**
- `clock` - Time display
- `weather` - Weather information
- `calendar` - Calendar view
- `note` - Text note

**Response:** `201 Created`
```json
{
  "data": {
    "id": "widget-123",
    "type": "clock",
    "x": 100,
    "y": 150
  }
}
```

---

### Update Widget
Update a widget's position and properties.

```http
PUT /api/dashboard/widgets/:id
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "x": 200,
  "y": 300,
  "data": {}
}
```

**Response:** `200 OK`
```json
{
  "data": {
    "id": "widget-123",
    "type": "clock",
    "x": 200,
    "y": 300
  }
}
```

---

### Delete Widget
Remove a widget from the dashboard.

```http
DELETE /api/dashboard/widgets/:id
Authorization: Bearer <jwt_token>
```

**Response:** `200 OK`
```json
{
  "data": {
    "id": "widget-123",
    "message": "Widget deleted"
  }
}
```

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request succeeded |
| 201 | Created - Resource created successfully |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Missing or invalid token |
| 403 | Forbidden - Access denied |
| 404 | Not Found - Resource not found |
| 422 | Unprocessable Entity - Validation failed |
| 500 | Internal Server Error |

---

## Error Examples

### Missing Authorization Header
```json
{
  "error": "Error 401",
  "message": "missing or malformed jwt",
  "code": 401
}
```

### Invalid Token
```json
{
  "error": "Error 401",
  "message": "invalid token",
  "code": 401
}
```

### Not Found
```json
{
  "error": "Error 404",
  "message": "user not found",
  "code": 404
}
```

---

## Rate Limiting
Currently no rate limiting. This should be added before production deployment.

## CORS
CORS is enabled for all origins. In production, restrict to specific domains.

## Future Enhancements
- [ ] WebSocket support for real-time updates
- [ ] File upload endpoints
- [ ] Widget sharing
- [ ] Dashboard templates
- [ ] Analytics endpoints
- [ ] Admin endpoints
