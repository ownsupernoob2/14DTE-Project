# Smart Mirror Frontend

React + Vite web application for the Smart Mirror project.

## Features

- React Router for page navigation
- Dashboard with draggable widgets
- Auto-hiding navbar (shows when mouse near top, hides after 10 seconds)
- Login/Register authentication pages
- User preferences page
- Black background with modern UI
- Responsive design

## Project Structure

```
src/
├── pages/           # Page components (Login, Register, Dashboard, Preferences)
├── components/      # Reusable components (Navbar, WidgetContainer)
├── styles/          # CSS files (organized by feature)
├── App.jsx          # Main app with routing
└── main.jsx         # Entry point
```

## Setup

### Prerequisites
- Node.js 16+ 
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint code
npm run lint
```

## Development

The app uses:
- **React Router v6** - Page routing
- **React Hooks** - State management (useState, useRef)
- **CSS Modules** - Component styling
- **Vite** - Build tool and dev server

## Pages

- `/` or `/dashboard` - Main dashboard with draggable widgets (requires auth)
- `/login` - Login page
- `/register` - Registration page
- `/preferences` - User preferences page (requires auth)

## Components

### Navbar
Auto-hiding navbar that appears when mouse is near the top and hides after 10 seconds of inactivity.

### WidgetContainer
Draggable widget component that supports:
- Moving widgets freely around the dashboard
- Closing widgets
- Different widget types (clock, weather, calendar, note)

### Dashboard
Main dashboard with:
- Plus button to add new widgets
- Widget menu for selecting widget types
- Drag-and-drop functionality

## API Integration

Currently uses dummy data. To connect to the Golang API:

1. Update authentication handlers to call `/api/auth/login` and `/api/auth/register`
2. Implement user context/state management for Auth0 tokens
3. Update Dashboard to fetch widgets from `/api/dashboard/widgets`
4. Implement widget CRUD operations

## Next Steps

- [ ] Integrate Auth0 authentication
- [ ] Connect to Golang API
- [ ] Add real widget functionality (clock, weather, calendar)
- [ ] Add unit tests
- [ ] Implement real-time updates
- [ ] Add offline support
