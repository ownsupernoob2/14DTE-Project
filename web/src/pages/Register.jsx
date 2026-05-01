import { Link } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import '../styles/pages.css'

export default function Register() {
  const { loginWithRedirect } = useAuth0()

  return (
    <div className="auth-page">
      <div className="auth-container">
        <h1>Register</h1>
        <p>Create a new account using Auth0.</p>
        <button 
          onClick={() => loginWithRedirect({ authorizationParams: { screen_hint: 'signup' } })}
          className="auth0-btn"
        >
          Sign Up with Auth0
        </button>
        <p>
          Already have an account? <Link to="/login">Login here</Link>
        </p>
      </div>
    </div>
  )
}
