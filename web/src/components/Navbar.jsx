import { useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'

export default function Navbar() {
  const [isVisible, setIsVisible] = useState(false)
  const timeoutRef = useRef(null)
  const navRef = useRef(null)

  const handleMouseMove = (e) => {
    // Show navbar if mouse is near top
    if (e.clientY < 50) {
      setIsVisible(true)
      clearTimeout(timeoutRef.current)
    } else if (isVisible) {
      // Start timer to hide navbar when mouse leaves
      clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(() => {
        setIsVisible(false)
      }, 10000)
    }
  }

  const handleMouseEnterNav = () => {
    clearTimeout(timeoutRef.current)
    setIsVisible(true)
  }

  const handleMouseLeaveNav = () => {
    clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => {
      setIsVisible(false)
    }, 10000)
  }

  return (
    <>
      <div
        onMouseMove={handleMouseMove}
        className="fixed left-0 right-0 top-0 z-40 h-12"
      />

      <AnimatePresence>
        {isVisible && (
          <motion.nav
            ref={navRef}
            initial={{ y: -80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -80, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed left-0 right-0 top-0 z-50 border-b border-white/10 bg-black/90 backdrop-blur"
            onMouseEnter={handleMouseEnterNav}
            onMouseLeave={handleMouseLeaveNav}
          >
            <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
              <Link to="/" className="text-sm font-semibold uppercase tracking-[0.3em] text-white">
                Smart Mirror
              </Link>
              <div className="flex items-center gap-6 text-xs uppercase tracking-[0.3em] text-white/70">
                <Link to="/dashboard" className="transition hover:text-white">
                  Dashboard
                </Link>
                <Link to="/preferences" className="transition hover:text-white">
                  Preferences
                </Link>
              </div>
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </>
  )
}
