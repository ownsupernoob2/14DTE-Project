import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import './App.css'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Simulator from './pages/Simulator'
import { ServerStatusProvider, useServerStatus } from './contexts/ServerStatusContext'
import { motion, AnimatePresence } from 'framer-motion'

function ServerDownNotice() {
  const { isServerUp } = useServerStatus()
  return (
    <AnimatePresence>
      {!isServerUp && (
        <motion.div
          initial={{ opacity: 0, y: 50, x: -20 }}
          animate={{ opacity: 1, y: 0, x: 0 }}
          exit={{ opacity: 0, y: 50, x: -20 }}
          style={{
            position: 'fixed',
            bottom: '20px',
            left: '20px',
            background: '#ef4444',
            color: 'white',
            padding: '12px 20px',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            zIndex: 9999,
            fontWeight: 'bold',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
            <line x1="12" y1="9" x2="12" y2="13"></line>
            <line x1="12" y1="17" x2="12.01" y2="17"></line>
          </svg>
          The Smart Mirror server is offline
        </motion.div>
      )}
    </AnimatePresence>
  )
}

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
    <ServerStatusProvider>
      <Router>
        <ServerDownNotice />
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
            path="/settings"
            element={isAuthenticated ? <Settings /> : <Navigate to="/login" />}
          />
          
          <Route path="/simulator" element={<Simulator />} />
          
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Router>
    </ServerStatusProvider>
  )
}

export default App
