import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

export default function Navbar({ activeTab, onTabClick }) {
  const location = useLocation()
  const navigate = useNavigate()

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', path: '/dashboard' },
    { id: 'timetable', label: 'Timetable', path: '/timetable' },
    { id: 'notices', label: 'Notices', path: '/notices' },
  ]

  const isSettings = location.pathname === '/settings'
  
  let currentTab = null
  if (location.pathname === '/dashboard' || location.pathname === '/') {
    currentTab = 'dashboard'
  } else if (location.pathname === '/timetable') {
    currentTab = 'timetable'
  } else if (location.pathname === '/notices') {
    currentTab = 'notices'
  } else if (!isSettings && activeTab) {
    currentTab = activeTab
  }

  const handleTabClick = (tab) => {
    navigate(tab.path)
    if (onTabClick) onTabClick(tab.id)
  }

  return (
    <header className="bg-[#0a0a0a] border-b border-[#1c1c1c] flex justify-between items-center w-full px-6 h-14 shrink-0 z-50 relative select-none">
      {/* Brand Logo (no star logo) */}
      <div className="flex items-center gap-4">
        <Link to="/dashboard" className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
          Smart Mirror
        </Link>
      </div>

      {/* Navigation tabs */}
      <div className="flex items-center gap-6 hidden md:flex h-full">
        <nav className="flex gap-6 h-full items-center">
          {tabs.map((tab) => {
            const isActive = currentTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab)}
                className={`relative py-4 px-1 text-xs uppercase tracking-wider transition-colors cursor-pointer outline-none font-semibold ${
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
          to="/settings"
          aria-label="settings"
          className={`p-2 rounded-full cursor-pointer active:scale-95 flex items-center justify-center transition-colors ${
            isSettings ? 'text-[#4fc3ff] bg-white/10' : 'text-[#8f8f8f] hover:text-white hover:bg-white/5'
          }`}
        >
          <span className="material-symbols-outlined text-xl" data-icon="account_circle">account_circle</span>
        </Link>
      </div>
    </header>
  )
}
