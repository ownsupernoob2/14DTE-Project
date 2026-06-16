import { useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { AnimatePresence, motion } from 'framer-motion'
import Navbar from '../components/Navbar'
import FaceCaptureModal from '../components/FaceCaptureModal'
import { useServerStatus } from '../contexts/ServerStatusContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

export default function Settings() {
  const { user, logout, getAccessTokenSilently } = useAuth0()
  const [showFaceModal, setShowFaceModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const { isServerUp } = useServerStatus()
  const [isDeleting, setIsDeleting] = useState(false)

  const lastScan = localStorage.getItem('lastFaceScan')
  const scanTime = lastScan ? parseInt(lastScan, 10) : 0
  const isScanRecent = (Date.now() - scanTime) < 24 * 60 * 60 * 1000

  const hoursUntilUpdate = isScanRecent
    ? Math.ceil((24 * 60 * 60 * 1000 - (Date.now() - scanTime)) / (60 * 60 * 1000))
    : 0

  const confirmDeleteFace = async () => {
    setIsDeleting(true)
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/faces/me`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        localStorage.removeItem('lastFaceScan')
        setShowDeleteConfirm(false)
        window.location.reload()
      } else {
        alert('Failed to delete face data. Please try again.')
      }
    } catch {
      alert('Error connecting to server')
    } finally {
      setIsDeleting(false)
    }
  }

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
          <h1 className="text-title">Settings</h1>

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
              <div style={{ color: 'rgba(148,163,184,0.9)', background: 'rgba(255,255,255,0.04)', padding: '14px 16px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)' }}>
                <strong style={{ display: 'block', marginBottom: '6px', color: '#e2e8f0', fontSize: '0.9rem' }}>Face registered</strong>
                <span style={{ fontSize: '0.85rem', lineHeight: 1.6 }}>
                  You can update your existing face scan again in about {hoursUntilUpdate} hour{hoursUntilUpdate !== 1 ? 's' : ''}.
                  To register a new scan sooner, delete your face data below — this permanently removes your encoding and lets you scan again immediately.
                </span>

                <div style={{ marginTop: '14px' }}>
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={isDeleting || !isServerUp}
                    style={{ padding: '7px 14px', fontSize: '0.8rem', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#f87171', cursor: 'pointer' }}
                  >
                    Delete Face Data
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <button
                  className="modern-btn"
                  onClick={() => setShowFaceModal(true)}
                  disabled={!isServerUp}
                  style={{ opacity: isServerUp ? 1 : 0.5, cursor: isServerUp ? 'pointer' : 'not-allowed', marginBottom: '12px' }}
                >
                  {isServerUp ? 'Register Face Scan' : 'Server Offline'}
                </button>

                <div>
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={isDeleting || !isServerUp}
                    style={{ padding: '7px 14px', fontSize: '0.8rem', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#f87171', cursor: 'pointer' }}
                  >
                    Delete Face Data
                  </button>
                </div>
              </div>
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

      <AnimatePresence>
        {showDeleteConfirm && (
          <motion.div
            className="fc-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => e.target === e.currentTarget && !isDeleting && setShowDeleteConfirm(false)}
          >
            <motion.div
              className="fc-modal"
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              style={{ maxWidth: '420px', padding: '28px 32px' }}
              onClick={(e) => e.stopPropagation()}
            >
              <p className="fc-overline">Delete Face Data</p>
              <h2 className="fc-title" style={{ fontSize: '1.2rem', marginBottom: '12px' }}>Are you sure?</h2>
              <p className="fc-sub" style={{ marginBottom: '24px' }}>
                This permanently deletes your face encoding from our servers. You will no longer be recognised by the mirror until you register again.
                {isScanRecent && (
                  <> You can register a new scan immediately after deletion.</>
                )}
              </p>
              <div className="fc-row-btns">
                <button
                  className="fc-btn fc-btn-outline"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={isDeleting}
                >
                  Cancel
                </button>
                <button
                  className="fc-btn"
                  onClick={confirmDeleteFace}
                  disabled={isDeleting || !isServerUp}
                  style={{ background: 'rgba(239,68,68,0.85)', border: 'none' }}
                >
                  {isDeleting ? 'Deleting...' : 'Delete permanently'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
