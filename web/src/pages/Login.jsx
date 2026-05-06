import { useAuth0 } from '@auth0/auth0-react'

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
      </div>
    </div>
  )
}
