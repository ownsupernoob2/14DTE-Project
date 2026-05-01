import { Link } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import '../styles/pages.css'

export default function Login() {
  const { loginWithRedirect } = useAuth0()

  return (
    <div className="auth-page">
      <div className="auth-container">
        <h1>Login</h1>
        <p>Login with your Auth0 account to access the Smart Mirror.</p>
        <button 
          onClick={() => loginWithRedirect()}
          className="auth0-btn"
        >
          Sign In with Auth0
        </button>
        <p>
          Don't have an account? <span className="link-like" onClick={() => loginWithRedirect({ authorizationParams: { screen_hint: 'signup' } })}>Register here</span>
        </p>
      </div>
    </div>
  )
}
