import '../styles/pages.css'

export default function Preferences() {
  return (
    <div className="preferences-page">
      <div className="preferences-container">
        <h1>Preferences</h1>
        
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
          <button>Change Password</button>
          <button>Two-Factor Authentication</button>
          <button className="danger-btn">Logout</button>
        </section>
      </div>
    </div>
  )
}
