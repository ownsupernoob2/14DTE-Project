import { useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { motion } from 'framer-motion'
import Navbar from '../components/Navbar'
import FaceCaptureModal from '../components/FaceCaptureModal'
import { useServerStatus } from '../contexts/ServerStatusContext'

export default function Preferences() {
  const { user, logout } = useAuth0()
  const [showFaceModal, setShowFaceModal] = useState(false)
  const { isServerUp } = useServerStatus()

  const lastScan = localStorage.getItem('lastFaceScan')
  const scanTime = lastScan ? parseInt(lastScan, 10) : 0
  const isScanRecent = (Date.now() - scanTime) < 24 * 60 * 60 * 1000

  return (
    <div className="preferences-container">
      <Navbar />
      <div className="preferences-content">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="glass-panel preferences-card"
        >
          <h1 className="text-title">Preferences</h1>

          {user && (
            <section className="pref-section user-profile">
              <img src={user.picture} alt={user.name} className="profile-img" />
              <div>
                <h3 className="profile-name">{user.name}</h3>
                <p className="profile-email">{user.email}</p>
              </div>
            </section>
          )}

          <section className="pref-section pref-section-block">
            <h2 className="text-overline">Face Registration</h2>
            <p className="text-subtitle" style={{ fontSize: '0.85rem', marginBottom: '16px' }}>
              Register your face so the smart mirror can identify you and load your dashboard.
            </p>
            {isScanRecent ? (
              <div style={{ color: '#4ade80', background: 'rgba(74, 222, 128, 0.1)', padding: '12px 16px', borderRadius: '8px', border: '1px solid rgba(74, 222, 128, 0.2)' }}>
                <strong style={{ display: 'block', marginBottom: '4px' }}>✓ Face Registered Successfully</strong>
                <span style={{ fontSize: '0.85rem', opacity: 0.9 }}>Your face scan was successful. To prevent spam, you can update your face scan again in 24 hours.</span>
              </div>
            ) : (
              <button 
                className="modern-btn" 
                onClick={() => setShowFaceModal(true)}
                disabled={!isServerUp}
                style={{ opacity: isServerUp ? 1 : 0.5, cursor: isServerUp ? 'pointer' : 'not-allowed' }}
              >
                {isServerUp ? "Register Face Scan" : "Server Offline"}
              </button>
            )}
          </section>

          <section className="pref-grid">
            <div className="pref-section">
              <h2 className="text-overline">Theme</h2>
              <div className="pref-options">
                <label className="pref-radio">
                  <input type="radio" name="theme" value="dark" defaultChecked />
                  Dark Mode
                </label>
                <label className="pref-radio">
                  <input type="radio" name="theme" value="light" />
                  Light Mode
                </label>
              </div>
            </div>

            <div className="pref-section">
              <h2 className="text-overline">Language</h2>
              <select defaultValue="en" className="pref-select">
                <option value="en">English</option>
                <option value="es">Spanish</option>
                <option value="fr">French</option>
                <option value="de">German</option>
              </select>
            </div>
          </section>

          <section className="pref-section pref-section-block">
            <h2 className="text-overline">Account</h2>
            <button
              className="modern-btn modern-btn-outline logout-btn"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
            >
              Logout
            </button>
          </section>
        </motion.div>
      </div>

      <FaceCaptureModal isOpen={showFaceModal} onClose={() => setShowFaceModal(false)} />
    </div>
  )
}
