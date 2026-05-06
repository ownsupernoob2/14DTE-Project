import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import './App.css'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Preferences from './pages/Preferences'

function App() {
  const { isAuthenticated, isLoading } = useAuth0()

  if (isLoading) {
    return (
      <div className="app-loading">
        Loading
      </div>
    )
  }

  return (
    <Router>
      <Routes>
        <Route path="/login" element={!isAuthenticated ? <Login /> : <Navigate to="/dashboard" />} />
        
        <Route
          path="/"
          element={isAuthenticated ? <Navigate to="/dashboard" /> : <Navigate to="/login" />}
        />
        <Route
          path="/dashboard"
          element={isAuthenticated ? <Dashboard /> : <Navigate to="/login" />}
        />
        <Route
          path="/preferences"
          element={isAuthenticated ? <Preferences /> : <Navigate to="/login" />}
        />
        
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  )
}

export default App
