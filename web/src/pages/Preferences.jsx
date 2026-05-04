import { useAuth0 } from '@auth0/auth0-react'
import { motion } from 'framer-motion'
import Navbar from '../components/Navbar'

export default function Preferences() {
  const { user, logout } = useAuth0()

  return (
    <div className="min-h-screen bg-black text-white">
      <Navbar />
      <div className="mx-auto max-w-4xl px-6 pt-28 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="rounded-3xl border border-white/10 bg-mirror-gray/90 p-8 shadow-soft"
        >
          <h1 className="text-3xl font-semibold">Preferences</h1>

          {user && (
            <section className="mt-6 flex items-center gap-4 rounded-2xl border border-white/10 bg-black/40 p-4">
              <img
                src={user.picture}
                alt={user.name}
                className="h-16 w-16 rounded-full border border-white/20"
              />
              <div>
                <h3 className="text-lg font-medium">{user.name}</h3>
                <p className="text-sm text-white/60">{user.email}</p>
              </div>
            </section>
          )}

          <section className="mt-8 grid gap-6 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-black/40 p-5">
              <h2 className="text-xs uppercase tracking-[0.3em] text-white/60">Theme</h2>
              <div className="mt-4 space-y-3 text-sm">
                <label className="flex items-center gap-2">
                  <input type="radio" name="theme" value="dark" defaultChecked />
                  Dark Mode
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="theme" value="light" />
                  Light Mode
                </label>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-black/40 p-5">
              <h2 className="text-xs uppercase tracking-[0.3em] text-white/60">Language</h2>
              <select
                defaultValue="en"
                className="mt-4 w-full rounded-xl border border-white/10 bg-black/60 p-3 text-sm"
              >
                <option value="en">English</option>
                <option value="es">Spanish</option>
                <option value="fr">French</option>
                <option value="de">German</option>
              </select>
            </div>
          </section>

          <section className="mt-6 rounded-2xl border border-white/10 bg-black/40 p-5">
            <h2 className="text-xs uppercase tracking-[0.3em] text-white/60">Notifications</h2>
            <div className="mt-4 grid gap-3 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" defaultChecked />
                Email Notifications
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" defaultChecked />
                Push Notifications
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" />
                Calendar Reminders
              </label>
            </div>
          </section>

          <section className="mt-6 rounded-2xl border border-white/10 bg-black/40 p-5">
            <h2 className="text-xs uppercase tracking-[0.3em] text-white/60">Account</h2>
            <button
              className="mt-4 w-full rounded-full border border-white/30 py-3 text-xs uppercase tracking-[0.35em] text-white"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
            >
              Logout
            </button>
          </section>
        </motion.div>
      </div>
    </div>
  )
}
