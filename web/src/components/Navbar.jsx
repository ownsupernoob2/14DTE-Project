import { useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'

export default function Navbar() {
  const [isVisible, setIsVisible] = useState(false)
  const timeoutRef = useRef(null)
  const navRef = useRef(null)

  const handleMouseMove = (e) => {
    if (e.clientY < 50) {
      setIsVisible(true)
      clearTimeout(timeoutRef.current)
    } else if (isVisible) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(() => setIsVisible(false), 10000)
    }
  }

  const handleMouseEnterNav = () => {
    clearTimeout(timeoutRef.current)
    setIsVisible(true)
  }

  const handleMouseLeaveNav = () => {
    clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setIsVisible(false), 10000)
  }

  return (
    <>
      <div onMouseMove={handleMouseMove} className="navbar-trigger" />
      <AnimatePresence>
        {isVisible && (
          <motion.nav
            ref={navRef}
            initial={{ y: -80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -80, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="navbar"
            onMouseEnter={handleMouseEnterNav}
            onMouseLeave={handleMouseLeaveNav}
          >
            <div className="navbar-content">
              <Link to="/" className="navbar-brand">Smart Mirror</Link>
              <div className="navbar-links">
                <Link to="/dashboard" className="nav-link">Dashboard</Link>
                <Link to="/preferences" className="nav-link">Preferences</Link>
              </div>
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </>
  )
}
