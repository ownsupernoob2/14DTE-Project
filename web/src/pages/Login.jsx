import { Link } from 'react-router-dom'
import '../styles/pages.css'

export default function Login() {
  return (
    <div className="auth-page">
      <div className="auth-container">
        <h1>Login</h1>
        <form>
          <input type="email" placeholder="Email" required />
          <input type="password" placeholder="Password" required />
          <button type="submit">Login</button>
        </form>
        <p>
          Don't have an account? <Link to="/register">Register here</Link>
        </p>
      </div>
    </div>
  )
}
