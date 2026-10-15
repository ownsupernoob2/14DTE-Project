import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import './App.css'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Privacy from './pages/Privacy'
import AdminAnalytics from './pages/AdminAnalytics'
import { ServerStatusProvider, useServerStatus } from './contexts/ServerStatusContext'
import { motion, AnimatePresence } from 'framer-motion'

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
            <span className="bg-[#ef4444] text-black font-mono font-bold text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-sm">
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
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Privacy />} />

          <Route
            path="/"
            element={isAuthenticated ? <Navigate to="/dashboard" /> : <Navigate to="/login" />}
          />
          <Route
            path="/dashboard"
            element={isAuthenticated ? <Dashboard defaultTab="dashboard" /> : <Navigate to="/login" />}
          />
          <Route
            path="/timetable"
            element={isAuthenticated ? <Dashboard defaultTab="timetable" /> : <Navigate to="/login" />}
          />
          <Route
            path="/notices"
            element={isAuthenticated ? <Dashboard defaultTab="notices" /> : <Navigate to="/login" />}
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
        {/* Subtle version code displayed in corner */}
        <div className="fixed bottom-2 right-3 text-[#444444] text-[11px] font-mono tracking-wider select-none pointer-events-none z-40">
          v1.2.0
        </div>
      </Router>
    </ServerStatusProvider>
  )
}

export default App
