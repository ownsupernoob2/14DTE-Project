import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

export default function Navbar({ activeTab = 'dashboard', onTabClick }) {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'timetable', label: 'Timetable' },
    { id: 'notices', label: 'Notices' },
    { id: 'kings-week', label: "King's Week" },
  ]

  return (
    <header className="bg-surface-dim border-b border-outline-variant shadow-sm flex justify-between items-center w-full px-6 h-16 shrink-0 z-50 relative">
      {/* Brand Logo */}
      <div className="flex items-center gap-4">
        <Link to="/dashboard" className="font-headline-lg text-2xl font-bold text-primary font-body-lg tracking-tight select-none">
          Smart Mirror
        </Link>
      </div>

      {/* Navigation tabs */}
      <div className="flex items-center gap-6 hidden md:flex h-full">
        <nav className="flex gap-6 h-full items-center">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => onTabClick && onTabClick(tab.id)}
                className={`relative py-5 px-1 font-body-lg text-sm transition-colors cursor-pointer select-none outline-none ${
                  isActive ? 'text-primary font-bold' : 'text-on-surface-variant font-medium hover:text-primary'
                }`}
              >
                {tab.label}
                {isActive && (
                  <motion.div
                    layoutId="activeNavbarTab"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-4">
        <button
          aria-label="notifications"
          className="text-primary hover:bg-surface-container-highest transition-colors p-2 rounded-full cursor-pointer active:scale-95 flex items-center justify-center"
        >
          <span className="material-symbols-outlined text-2xl" data-icon="notifications">notifications</span>
        </button>
        <Link
          to="/settings"
          aria-label="settings"
          className="text-primary hover:bg-surface-container-highest transition-colors p-2 rounded-full cursor-pointer active:scale-95 flex items-center justify-center"
        >
          <span className="material-symbols-outlined text-2xl" data-icon="account_circle">account_circle</span>
        </Link>
      </div>
    </header>
  )
}
