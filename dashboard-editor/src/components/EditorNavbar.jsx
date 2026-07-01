import { useAuth0 } from '@auth0/auth0-react'
import { motion } from 'framer-motion'

export default function EditorNavbar({ onSave, isSaving, widgetCount, onOpenSettings }) {
  const { user } = useAuth0()

  return (
    <nav className="editor-navbar">
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 9, flexShrink: 0,
          background: 'linear-gradient(135deg, #4f8ef7 0%, #7c5af8 100%)',
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, padding: 8,
          boxShadow: '0 0 18px rgba(79,142,247,0.30)',
        }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} style={{ background: 'rgba(255,255,255,0.88)', borderRadius: 2 }} />
          ))}
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: '0.88rem', letterSpacing: '-0.01em', lineHeight: 1.2 }}>
            Mirror Layout
          </div>
          <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.04em' }}>
            6 × 6 grid editor
          </div>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Widget count */}
      <div style={{
        fontSize: '0.73rem', color: 'var(--text-muted)',
        background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)',
        borderRadius: 9999, padding: '4px 14px',
      }}>
        {widgetCount} / {6 * 6} cells used
      </div>

      {/* Save */}
      <motion.button
        className="btn btn-primary"
        onClick={onSave}
        disabled={isSaving}
        whileTap={{ scale: 0.96 }}
        style={{ fontSize: '0.8rem', padding: '7px 18px' }}
      >
        {isSaving ? (
          <>
            <motion.span animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.8, ease: 'linear' }}
              style={{ display: 'inline-block' }}>
              ⟳
            </motion.span>
            Saving…
          </>
        ) : (
          <>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            Save Layout
          </>
        )}
      </motion.button>

      {/* Avatar → Settings */}
      {user && (
        <motion.button
          className="avatar-btn"
          onClick={onOpenSettings}
          whileTap={{ scale: 0.94 }}
          title="Open Settings"
          style={{ background: 'none', border: '2px solid var(--border-mid)' }}
        >
          {user.picture ? (
            <img src={user.picture} alt={user.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <div style={{
              width: '100%', height: '100%', background: 'var(--accent)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.75rem', fontWeight: 700, color: '#fff',
            }}>
              {(user.name || user.email || '?')[0].toUpperCase()}
            </div>
          )}
        </motion.button>
      )}
    </nav>
  )
}
