import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'

export default function Login() {
  const { loginWithRedirect, error } = useAuth0()

  return (
    <div className="auth-container">
      <div className="glass-panel auth-card" style={{ textAlign: 'center' }}>
        <h1 className="text-title auth-title">Smart Mirror</h1>
        <p className="text-subtitle" style={{ marginBottom: '32px' }}>
          Student Login
        </p>

        {error && (
          <div style={{ color: '#ef4444', marginBottom: '24px', fontSize: '0.875rem' }}>
            <p><strong>Login Error:</strong></p>
            <p>{error.message}</p>
          </div>
        )}

        <div className="auth-buttons">
          <button
            onClick={() => loginWithRedirect()}
            className="modern-btn"
          >
            Log In
          </button>
        </div>

        <div style={{ marginTop: '24px', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px' }}>
          <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5, margin: '0 0 8px 0' }}>
            By signing up or logging in, you agree to our{' '}
            <Link to="/privacy" style={{ color: 'var(--accent)', textDecoration: 'underline', fontWeight: 500 }}>
              Privacy Policy &amp; Terms
            </Link>.
          </p>
          <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.45)', fontStyle: 'italic', margin: 0 }}>
            "Using the mirror/personalising it by signing up is entirely optional."
          </p>
        </div>
      </div>
    </div>
  )
}
