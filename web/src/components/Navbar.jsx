import { Link, useLocation } from 'react-router-dom'
import { useMe } from '../contexts/MeContext'
import { useLanguage } from '../contexts/LanguageContext'

export default function Navbar() {
  const location = useLocation()
  const { isAdmin } = useMe()
  const { t } = useLanguage()

  const isSettings = location.pathname === '/settings'
  const isAdminPath = location.pathname === '/admin'

  return (
    <header className="bg-[#000000] border-b border-[#1c1c1c] flex justify-between items-center w-full px-6 h-14 shrink-0 z-50 relative select-none">
      {/* Brand Title (Monochrome, sharp) */}
      <div className="flex items-center gap-3">
        <Link to="/dashboard" className="text-sm font-mono font-bold uppercase tracking-wider text-white hover:text-[#cccccc] transition-colors">
          {t('brand')}
        </Link>
      </div>

      {/* Action buttons (Sharp, All Caps, Monochrome, No Blue) */}
      <div className="flex items-center gap-3">
        {isAdmin && (
          <Link
            to="/admin"
            className={`px-3 py-1.5 border font-mono text-xs font-bold uppercase tracking-wider transition-colors rounded-none ${
              isAdminPath
                ? 'bg-white text-black border-white'
                : 'bg-[#000000] text-[#888888] border-[#222222] hover:text-white hover:border-[#444444]'
            }`}
          >
            {t('admin')}
          </Link>
        )}
        <Link
          to="/settings"
          aria-label="Settings"
          className={`px-3 py-1.5 border font-mono text-xs font-bold uppercase tracking-wider transition-colors rounded-none flex items-center gap-1.5 ${
            isSettings
              ? 'bg-white text-black border-white'
              : 'bg-[#000000] text-[#888888] border-[#222222] hover:text-white hover:border-[#444444]'
          }`}
        >
          <span className="material-symbols-outlined text-sm leading-none">settings</span>
          <span>{t('settings')}</span>
        </Link>
      </div>
    </header>
  )
}
