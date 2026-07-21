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
    <header className="bg-[#0a0a0a] border-b border-[#1c1c1c] flex justify-between items-center w-full px-6 h-14 shrink-0 z-50 relative">
      {/* Brand Logo */}
      <div className="flex items-center gap-4">
        <Link to="/dashboard" className="text-xl font-bold text-white tracking-tight select-none flex items-center gap-2">
          <span className="text-[#4fc3ff]">✦</span> Smart Mirror
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
                className={`relative py-4 px-1 text-xs uppercase tracking-wider transition-colors cursor-pointer select-none outline-none font-semibold ${
                  isActive ? 'text-[#4fc3ff]' : 'text-[#8f8f8f] hover:text-[#d0d0d0]'
                }`}
              >
                {tab.label}
                {isActive && (
                  <motion.div
                    layoutId="activeNavbarTab"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#4fc3ff]"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-3">
        <Link
          to="/simulator"
          className="text-xs px-3 py-1.5 rounded-full border border-[#333] text-[#d0d0d0] hover:border-[#4fc3ff] hover:text-[#4fc3ff] transition-colors"
        >
          Mirror View
        </Link>
        <Link
          to="/settings"
          aria-label="settings"
          className="text-[#8f8f8f] hover:text-white transition-colors p-2 rounded-full cursor-pointer active:scale-95 flex items-center justify-center"
        >
          <span className="material-symbols-outlined text-xl" data-icon="account_circle">account_circle</span>
        </Link>
      </div>
    </header>
  )
}

