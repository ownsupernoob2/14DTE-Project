import { useState, useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { AnimatePresence, motion } from 'framer-motion'
import Navbar from '../components/Navbar'
import FaceCaptureModal from '../components/FaceCaptureModal'
import BarcodeCaptureModal from '../components/BarcodeCaptureModal'
import { useServerStatus } from '../contexts/ServerStatusContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// ── Inline style constants (change here to restyle globally) ──────────────────
const S = {
  dangerBg:        'rgba(239, 68, 68, 0.08)',
  dangerBorder:    'rgba(239, 68, 68, 0.22)',
  dangerText:      '#f87171',
  dangerActiveBg:  'rgba(239, 68, 68, 0.18)',
  infoBoxBg:       'rgba(255, 255, 255, 0.03)',
  infoBoxBorder:   'rgba(255, 255, 255, 0.07)',
  mutedText:       'rgba(255,255,255,0.55)',
  subText:         'rgba(255,255,255,0.35)',
}

export default function Settings() {
  const { user, logout, getAccessTokenSilently } = useAuth0()
  const [showFaceModal, setShowFaceModal] = useState(false)
  const [showBarcodeModal, setShowBarcodeModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const { isServerUp } = useServerStatus()
  const [isDeleting, setIsDeleting] = useState(false)
  const [barcode, setBarcode] = useState('')
  const [loadingBarcode, setLoadingBarcode] = useState(true)

  const lastScan = localStorage.getItem('lastFaceScan')
  const scanTime = lastScan ? parseInt(lastScan, 10) : 0
  const isScanRecent = (Date.now() - scanTime) < 24 * 60 * 60 * 1000

  const hoursUntilUpdate = isScanRecent
    ? Math.ceil((24 * 60 * 60 * 1000 - (Date.now() - scanTime)) / (60 * 60 * 1000))
    : 0

  useEffect(() => {
    async function fetchBarcode() {
      try {
        const token = await getAccessTokenSilently()
        const res = await fetch(`${API_URL}/api/users/me/barcode`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (res.ok) {
          const data = await res.json()
          setBarcode(data.barcode || '')
        }
      } catch (err) {
        console.error('Failed to load barcode:', err)
      } finally {
        setLoadingBarcode(false)
      }
    }
    fetchBarcode()
  }, [getAccessTokenSilently])

  const handleBarcodeClick = () => {
    setShowBarcodeModal(true)
  }

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

          {/* ── Mirror Sign-In ──────────────────────────────────────────────── */}
          <section className="pref-section pref-section-block">
            <h2 className="text-overline">Mirror Sign-In</h2>
            <p className="text-subtitle" style={{ fontSize: '0.85rem', marginBottom: '16px' }}>
              Choose how the mirror recognises you. Face scan and barcode are both supported.
            </p>

            {/* Face registration */}
            {isScanRecent ? (
              <div style={{ background: S.infoBoxBg, padding: '14px 16px', borderRadius: '10px', border: `1px solid ${S.infoBoxBorder}`, marginBottom: '10px' }}>
                <strong style={{ display: 'block', marginBottom: '4px', color: 'var(--text-primary)', fontSize: '0.88rem' }}>Face scan registered</strong>
                <span style={{ fontSize: '0.82rem', lineHeight: 1.6, color: S.mutedText }}>
                  Can be updated in {hoursUntilUpdate} hour{hoursUntilUpdate !== 1 ? 's' : ''}. Delete your data below to re-scan immediately.
                </span>
              </div>
            ) : (
              <button
                className="modern-btn"
                onClick={() => setShowFaceModal(true)}
                disabled={!isServerUp}
                style={{ opacity: isServerUp ? 1 : 0.45, cursor: isServerUp ? 'pointer' : 'not-allowed', marginBottom: '10px' }}
              >
                {isServerUp ? 'Register Face Scan' : 'Server Offline'}
              </button>
            )}

            {/* Barcode sign-in */}
            <button
              className="modern-btn modern-btn-outline"
              onClick={handleBarcodeClick}
              style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              STUDENT BARCODE {barcode ? `(${barcode})` : ''}
            </button>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '320px' }}>
              <button
                className="modern-btn"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={isDeleting || !isServerUp}
                style={{
                  background: 'rgba(239, 68, 68, 0.85)',
                  border: '1px solid #ef4444',
                  color: 'white',
                  letterSpacing: '0.08em',
                  fontWeight: 600,
                  opacity: (isDeleting || !isServerUp) ? 0.5 : 1,
                  cursor: (isDeleting || !isServerUp) ? 'not-allowed' : 'pointer'
                }}
              >
                DELETE FACE DATA
              </button>

              <button
                className="modern-btn modern-btn-outline"
                onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
                style={{
                  borderColor: 'rgba(239, 68, 68, 0.4)',
                  color: '#f87171',
                  background: 'rgba(239, 68, 68, 0.05)',
                  letterSpacing: '0.08em',
                  fontWeight: 600
                }}
              >
                LOGOUT
              </button>
            </div>
          </section>
        </motion.div>
      </div>

      <FaceCaptureModal isOpen={showFaceModal} onClose={() => setShowFaceModal(false)} />
      <BarcodeCaptureModal isOpen={showBarcodeModal} onClose={() => setShowBarcodeModal(false)} onBarcodeSaved={(code) => setBarcode(code)} />

      {/* ── Delete confirmation modal ─────────────────────────────────────── */}
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
              onClick={(e) => e.stopPropagation()}
            >
              <div className="fc-phase fc-phase-center" style={{ justifyContent: 'center' }}>
                {/* Warning icon */}
                <div style={{
                  width: '48px', height: '48px', borderRadius: '50%',
                  background: S.dangerBg, border: `1px solid ${S.dangerBorder}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={S.dangerText} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                    <line x1="12" y1="9" x2="12" y2="13"/>
                    <line x1="12" y1="17" x2="12.01" y2="17"/>
                  </svg>
                </div>

                <p className="fc-overline" style={{ color: S.dangerText }}>Destructive Action</p>
                <h2 className="fc-title" style={{ fontSize: '1.35rem' }}>Delete Face Data?</h2>
                <p className="fc-sub">
                  This permanently removes your face encoding from our servers. You will no longer be recognised by the mirror until you register again.
                  {isScanRecent && <><br /><span style={{ color: S.mutedText, fontSize: '0.78rem', marginTop: '6px', display: 'block' }}>You can register a new scan immediately after deletion.</span></>}
                </p>

                <div style={{
                  background: S.dangerBg, border: `1px solid ${S.dangerBorder}`,
                  borderRadius: '10px', padding: '10px 14px', width: '100%',
                  fontSize: '0.78rem', color: S.dangerText, textAlign: 'left',
                }}>
                  This action cannot be undone.
                </div>

                <div className="fc-row-btns" style={{ marginTop: '4px' }}>
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
                    style={{ background: '#dc2626', border: 'none', color: '#fff' }}
                  >
                    {isDeleting ? 'Deleting...' : 'Delete permanently'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
