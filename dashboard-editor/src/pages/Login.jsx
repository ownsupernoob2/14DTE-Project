import { useAuth0 } from '@auth0/auth0-react'
import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'

export default function Login() {
  const { loginWithRedirect, error } = useAuth0()

  return (
    <div className="auth-page">
      {/* Background orbs */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', overflow: 'hidden', zIndex: 0,
      }}>
        <div style={{
          position: 'absolute', width: 600, height: 600, borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(109,40,217,0.13) 0%, transparent 70%)',
          top: '10%', left: '-10%', filter: 'blur(40px)',
        }} />
        <div style={{
          position: 'absolute', width: 500, height: 500, borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(56,189,248,0.10) 0%, transparent 70%)',
          top: '30%', right: '-5%', filter: 'blur(40px)',
        }} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="auth-card glass"
        style={{ position: 'relative', zIndex: 1 }}
      >
        {/* Logo grid icon */}
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 14,
            background: 'linear-gradient(135deg, #3b82f6 0%, #6d28d9 100%)',
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5, padding: 12,
            boxShadow: '0 0 24px rgba(59,130,246,0.35)',
          }}>
            {[...Array(4)].map((_, i) => (
              <div key={i} style={{ background: 'rgba(255,255,255,0.9)', borderRadius: 3 }} />
            ))}
          </div>
        </div>

        <h1 style={{ fontSize: '1.6rem', fontWeight: 700, marginBottom: 6, letterSpacing: '-0.02em' }}>
          Smart Mirror
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 28 }}>
          Layout Editor — sign in to customise your mirror
        </p>

        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)',
            borderRadius: 10, padding: '10px 14px', marginBottom: 20,
            color: '#f87171', fontSize: '0.8rem',
          }}>
            <strong>Login error:</strong> {error.message}
          </div>
        )}

        <button
          className="btn btn-primary"
          onClick={() => loginWithRedirect()}
          style={{ width: '100%', justifyContent: 'center', fontSize: '0.88rem', padding: '11px 20px' }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
            <polyline points="10 17 15 12 10 7" />
            <line x1="15" y1="12" x2="3" y2="12" />
          </svg>
          Log In with Auth0
        </button>

        <div style={{ marginTop: 24, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          <p style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.6 }}>
            By continuing you agree to our{' '}
            <a href="/privacy" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>
              Privacy Policy
            </a>.
            Using the mirror is entirely optional.
          </p>
        </div>
      </motion.div>
    </div>
  )
}
