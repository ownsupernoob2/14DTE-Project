import { useState, useRef } from 'react'
import '../styles/navbar.css'
import { Link } from 'react-router-dom'

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
      <div onMouseMove={handleMouseMove} style={{ position: 'fixed', top: 0, left: 0, right: 0, height: '50px', zIndex: 998 }} />
      
      <nav
        ref={navRef}
        className={`navbar ${isVisible ? 'visible' : 'hidden'}`}
        onMouseEnter={handleMouseEnterNav}
        onMouseLeave={handleMouseLeaveNav}
      >
        <div className="navbar-content">
          <Link to="/" className="navbar-brand">Smart Mirror</Link>
          <div className="navbar-links">
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/preferences">Preferences</Link>
          </div>
        </div>
      </nav>
    </>
  )
}
