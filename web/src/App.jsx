import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import './App.css'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Privacy from './pages/Privacy'
import AdminAnalytics from './pages/AdminAnalytics'
import { ServerStatusProvider, useServerStatus } from './contexts/ServerStatusContext'
import { LanguageProvider } from './contexts/LanguageContext'
import { motion, AnimatePresence } from 'framer-motion'

import { useState, useEffect } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

function ServerDownNotice() {
  const { isServerUp } = useServerStatus()
  return (
    <AnimatePresence>
      {!isServerUp && (
        <motion.aside
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.25 }}
          className="w-full bg-[#140a0a] border-b border-[#3b1212] px-6 py-2.5 flex items-center justify-between text-xs text-[#fca5a5] shrink-0 z-50 sticky top-0"
        >
          <div className="flex items-center gap-3">
            <span className="bg-[#ef4444] text-black font-mono font-bold text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-none">
              OFFLINE
            </span>
            <span className="font-sans font-medium text-[13px] text-white">
              The Smart Mirror server is offline. Real-time updates and timetable sync are temporarily paused.
            </span>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}

function App() {
  const { isAuthenticated, isLoading } = useAuth0()
  const [versionCode, setVersionCode] = useState('v1.2.1')

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then(res => res.json())
      .then(data => {
        if (data && data.version) {
          setVersionCode(data.version)
        }
      })
      .catch(() => {
        // Fallback to /api/health
        fetch(`${API_URL}/api/health`)
          .then(res => res.json())
          .then(data => {
            if (data && data.version) setVersionCode(data.version)
          })
          .catch(() => {})
      })
  }, [])

  if (isLoading) {
    return (
      <div className="app-loading">
        Loading
      </div>
    )
  }

  return (
    <LanguageProvider>
      <ServerStatusProvider>
        <Router>
          <ServerDownNotice />
          <Routes>
            <Route path="/login" element={!isAuthenticated ? <Login /> : <Navigate to="/dashboard" />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Privacy />} />

            <Route
              path="/"
              element={isAuthenticated ? <Navigate to="/dashboard" /> : <Navigate to="/login" />}
            />
            <Route
              path="/dashboard"
              element={isAuthenticated ? <Dashboard /> : <Navigate to="/login" />}
            />
            {/* Tab routes redirect directly to single unified dashboard */}
            <Route
              path="/timetable"
              element={<Navigate to="/dashboard" replace />}
            />
            <Route
              path="/notices"
              element={<Navigate to="/dashboard" replace />}
            />
            <Route
              path="/settings"
              element={isAuthenticated ? <Settings /> : <Navigate to="/login" />}
            />
            <Route
              path="/admin"
              element={isAuthenticated ? <AdminAnalytics /> : <Navigate to="/login" />}
            />

            <Route path="*" element={<Navigate to="/dashboard" />} />
          </Routes>
          <div className="fixed bottom-2 right-3 text-[#333333] text-[11px] font-mono tracking-wider select-none pointer-events-none z-40">
            {versionCode}
          </div>
        </Router>
      </ServerStatusProvider>
    </LanguageProvider>
  )
}

export default App
