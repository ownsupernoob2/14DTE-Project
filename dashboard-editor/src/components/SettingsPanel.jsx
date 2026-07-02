import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

export default function SettingsPanel({ open, onClose }) {
  const { user, logout, getAccessTokenSilently } = useAuth0()
  const [icsInput, setIcsInput]   = useState('')
  const [icsSaved, setIcsSaved]   = useState(() => localStorage.getItem('timetable_ics_url') || '')
  const [icsSaving, setIcsSaving] = useState(false)
  const [icsError,  setIcsError]  = useState(null)
  const [icsOk,     setIcsOk]     = useState(false)

  useEffect(() => {
    if (open) {
      setIcsInput(localStorage.getItem('timetable_ics_url') || '')
      setIcsError(null)
      setIcsOk(false)
    }
  }, [open])

  async function handleSaveIcs() {
    const url = icsInput.trim()
    if (!url) return
    setIcsSaving(true)
    setIcsError(null)
    setIcsOk(false)
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/timetable/ics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ics_url: url }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      localStorage.setItem('timetable_ics_url', url)
      // Clear cache so timetable refetches
      localStorage.removeItem('timetable_cache_date')
      localStorage.removeItem('timetable_cache_data')
      setIcsSaved(url)
      setIcsOk(true)
      setTimeout(() => setIcsOk(false), 2000)
    } catch (e) {
      setIcsError(e.message)
    } finally {
      setIcsSaving(false)
    }
  }

  function handleClearCache() {
    localStorage.removeItem('notices_date')
    localStorage.removeItem('notices_data')
    localStorage.removeItem('timetable_cache_date')
    localStorage.removeItem('timetable_cache_data')
    window.location.reload()
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{
              position: 'fixed', inset: 0, zIndex: 400,
              background: 'rgba(0,0,0,0.5)',
              backdropFilter: 'blur(4px)',
            }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            key="panel"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 340, damping: 34 }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 401,
              width: 340, background: 'var(--bg-2)',
              borderLeft: '1px solid var(--border)',
              overflowY: 'auto', padding: '28px 22px',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '1rem', letterSpacing: '-0.01em' }}>Settings</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Account & preferences</div>
              </div>
              <button
                onClick={onClose}
                style={{
                  background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)',
                  color: 'var(--text)', borderRadius: 9, width: 32, height: 32,
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            {/* User card */}
            {user && (
              <div style={{
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 16, padding: '16px', marginBottom: 20,
                display: 'flex', alignItems: 'center', gap: 13,
              }}>
                {user.picture ? (
                  <img src={user.picture} alt={user.name}
                    style={{ width: 46, height: 46, borderRadius: '50%', border: '2px solid var(--border-mid)', flexShrink: 0 }} />
                ) : (
                  <div style={{
                    width: 46, height: 46, borderRadius: '50%', background: 'var(--accent)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '1rem', fontWeight: 700, color: '#fff', flexShrink: 0,
                  }}>
                    {(user.name || user.email || '?')[0].toUpperCase()}
                  </div>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', marginBottom: 2,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {user.name || user.email}
                  </div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {user.email}
                  </div>
                </div>
              </div>
            )}

            {/* Timetable ICS URL */}
            <div style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 16, padding: '16px', marginBottom: 14,
            }}>
              <div className="section-hdr" style={{ marginBottom: 10 }}>Timetable Calendar URL</div>
              <p style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.55 }}>
                Paste your school timetable .ics URL to enable the Timetable widget.
              </p>
              {icsSaved && (
                <div style={{
                  fontSize: '0.65rem', color: 'var(--success)', marginBottom: 8,
                  background: 'rgba(34,201,160,0.08)', border: '1px solid rgba(34,201,160,0.2)',
                  borderRadius: 8, padding: '5px 10px',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  Current: {icsSaved}
                </div>
              )}
              <input
                className="field-input"
                value={icsInput}
                onChange={e => setIcsInput(e.target.value)}
                placeholder="https://..."
                style={{ marginBottom: 10 }}
              />
              {icsError && (
                <div style={{ fontSize: '0.68rem', color: '#f87171', marginBottom: 8 }}>{icsError}</div>
              )}
              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center', fontSize: '0.78rem' }}
                onClick={handleSaveIcs}
                disabled={icsSaving || !icsInput.trim()}
              >
                {icsOk ? (
                  <>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Saved
                  </>
                ) : icsSaving ? 'Saving…' : 'Save Calendar URL'}
              </button>
            </div>

            {/* Cache */}
            <div style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 16, padding: '16px', marginBottom: 14,
            }}>
              <div className="section-hdr" style={{ marginBottom: 8 }}>Data Cache</div>
              <p style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.55 }}>
                Notices and timetable are cached daily. Clear to force a refresh.
              </p>
              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', fontSize: '0.78rem' }}
                onClick={handleClearCache}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 .49-3.5" />
                </svg>
                Clear Cache & Reload
              </button>
            </div>

            {/* Divider */}
            <div className="divider" />

            {/* Logout */}
            <button
              className="btn btn-danger"
              style={{ width: '100%', justifyContent: 'center', fontSize: '0.8rem' }}
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin + '/login' } })}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              Sign Out
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
