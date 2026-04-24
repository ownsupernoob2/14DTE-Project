import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import './App.css'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Preferences from './pages/Preferences'

function App() {
  // TODO: Replace with actual auth check
  const isAuthenticated = true

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/"
          element={isAuthenticated ? <Dashboard /> : <Navigate to="/login" />}
        />
        <Route
          path="/dashboard"
          element={isAuthenticated ? <Dashboard /> : <Navigate to="/login" />}
        />
        <Route
          path="/preferences"
          element={isAuthenticated ? <Preferences /> : <Navigate to="/login" />}
        />
      </Routes>
    </Router>
  )
}

export default App
