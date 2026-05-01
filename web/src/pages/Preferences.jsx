import { useAuth0 } from '@auth0/auth0-react'
import '../styles/pages.css'
import Navbar from '../components/Navbar'

export default function Preferences() {
  const { user, logout } = useAuth0()

  return (
    <div className="preferences-page">
      <Navbar />
      <div className="preferences-container">
        <h1>Preferences</h1>
        
        {user && (
          <section className="preference-section profile-section">
            <img src={user.picture} alt={user.name} />
            <div>
              <h3>{user.name}</h3>
              <p>{user.email}</p>
            </div>
          </section>
        )}

        <section className="preference-section">
          <h2>Theme</h2>
          <label>
            <input type="radio" name="theme" value="dark" defaultChecked />
            Dark Mode
          </label>
          <label>
            <input type="radio" name="theme" value="light" />
            Light Mode
          </label>
        </section>

        <section className="preference-section">
          <h2>Language</h2>
          <select defaultValue="en">
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
          </select>
        </section>

        <section className="preference-section">
          <h2>Notifications</h2>
          <label>
            <input type="checkbox" defaultChecked />
            Email Notifications
          </label>
          <label>
            <input type="checkbox" defaultChecked />
            Push Notifications
          </label>
          <label>
            <input type="checkbox" />
            Calendar Reminders
          </label>
        </section>

        <section className="preference-section">
          <h2>Account</h2>
          <button className="danger-btn" onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>
            Logout
          </button>
        </section>
      </div>
    </div>
  )
}
