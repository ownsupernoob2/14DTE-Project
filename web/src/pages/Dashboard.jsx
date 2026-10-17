import { useState, useEffect, useRef } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import Navbar from '../components/Navbar'
import DailyNoticesWidget from '../components/DailyNoticesWidget'
import TimetableWidget from '../components/TimetableWidget'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// ─── Live Clock Header Row matching mirror aesthetic ─────────────────────────
function ClockRow() {
  const [now, setNow] = useState(new Date())
  
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const hours = String(now.getHours()).padStart(2, '0')
  const minutes = String(now.getMinutes()).padStart(2, '0')
  const seconds = String(now.getSeconds()).padStart(2, '0')
  const dateStr = now.toLocaleDateString('en-NZ', { weekday: 'short', day: 'numeric', month: 'short' })

  return (
    <div className="flex justify-between items-baseline font-mono pb-5 border-b border-[#1c1c1c] w-full select-none">
      <div className="flex flex-col">
        <span className="text-[11px] uppercase tracking-widest text-[#4fc3ff] font-semibold">Live System Clock</span>
        <span className="text-[18px] text-[#d0d0d0] font-sans font-medium">{dateStr}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-[44px] md:text-[48px] font-semibold text-white tracking-tight leading-none font-mono">{hours}:{minutes}</span>
        <span className="text-[18px] text-[#4fc3ff] font-mono leading-none">{seconds}</span>
      </div>
    </div>
  )
}

// ─── Student Onboarding & Readiness Banner ────────────────────────────────────
function StudentOnboardingBanner() {
  const navigate = useNavigate()
  const { getAccessTokenSilently } = useAuth0()
  const [barcode, setBarcode] = useState(null)
  const [hasFace, setHasFace] = useState(() => Boolean(localStorage.getItem('lastFaceScan')))
  const [hasTimetable, setHasTimetable] = useState(() => Boolean(localStorage.getItem('timetable_ics_url')))
  const [isDismissed, setIsDismissed] = useState(() => localStorage.getItem('onboarding_banner_dismissed') === 'true')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const checkStatus = async () => {
      try {
        const token = await getAccessTokenSilently()
        const res = await fetch(`${API_URL}/api/users/me/barcode`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (res.ok) {
          const data = await res.json()
          if (!cancelled) setBarcode(data.barcode || '')
        } else {
          if (!cancelled) setBarcode('')
        }
      } catch {
        if (!cancelled) setBarcode('')
      }

      // Also check timetable remote if not cached locally
      if (!localStorage.getItem('timetable_ics_url')) {
        try {
          const token = await getAccessTokenSilently()
          const res = await fetch(`${API_URL}/api/timetable/ics`, {
            headers: { Authorization: `Bearer ${token}` }
          })
          if (res.ok) {
            const data = await res.json()
            if (!cancelled && data.ics_url) {
              setHasTimetable(true)
              localStorage.setItem('timetable_ics_url', data.ics_url)
            }
          }
        } catch { /* silent */ }
      }

      if (!cancelled) setLoading(false)
    }

    checkStatus()
    return () => { cancelled = true }
  }, [getAccessTokenSilently])

  if (loading) return null

  const hasBarcode = Boolean(barcode && barcode.trim())
  const stepsDone = (hasBarcode ? 1 : 0) + (hasFace ? 1 : 0) + (hasTimetable ? 1 : 0)
  const isAllComplete = stepsDone === 3

  // If dismissed and all complete, render minimal subtle indicator
  if (isDismissed && isAllComplete) {
    return null
  }

  return (
    <motion.div 
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="w-full bg-[#080d12] border-b border-[#1e293b] px-6 py-3 shrink-0 select-none"
    >
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        {/* Left: Status & Headline */}
        <div className="flex items-center gap-3">
          <span className={`px-2.5 py-1 rounded text-[10px] font-mono font-bold tracking-wider uppercase ${
            isAllComplete 
              ? 'bg-[#10b981]/20 text-[#34d399] border border-[#10b981]/30' 
              : 'bg-[#4fc3ff]/15 text-[#4fc3ff] border border-[#4fc3ff]/30'
          }`}>
            {isAllComplete ? 'SYSTEM READY (3/3)' : `SETUP GUIDE (${stepsDone}/3 COMPLETE)`}
          </span>
          <div>
            <p className="text-[13px] text-white font-medium">
              {isAllComplete 
                ? 'Your student profile is fully configured for Smart Mirror recognition!' 
                : 'Complete your 3-step setup to unlock automatic mirror sign-in & timetable sync'}
            </p>
          </div>
        </div>

        {/* Middle: Step Badges / Quick Links */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Step 1: Barcode */}
          <button
            onClick={() => navigate('/settings')}
            className={`px-3 py-1 rounded text-xs font-mono transition-all flex items-center gap-1.5 cursor-pointer ${
              hasBarcode
                ? 'bg-[#0f172a] text-[#34d399] border border-[#059669]/40 hover:border-[#10b981]'
                : 'bg-[#1e1b4b]/60 text-[#c7d2fe] border border-[#6366f1]/40 hover:border-[#818cf8]'
            }`}
          >
            <span>{hasBarcode ? '✓' : '1.'}</span>
            <span>Student ID Barcode</span>
          </button>

          {/* Step 2: Face AI */}
          <button
            onClick={() => navigate('/settings')}
            className={`px-3 py-1 rounded text-xs font-mono transition-all flex items-center gap-1.5 cursor-pointer ${
              hasFace
                ? 'bg-[#0f172a] text-[#34d399] border border-[#059669]/40 hover:border-[#10b981]'
                : hasBarcode
                ? 'bg-[#1e1b4b]/60 text-[#c7d2fe] border border-[#6366f1]/40 hover:border-[#818cf8]'
                : 'bg-[#111827]/40 text-[#64748b] border border-[#334155]/40 cursor-not-allowed'
            }`}
          >
            <span>{hasFace ? '✓' : '2.'}</span>
            <span>Face Recognition</span>
          </button>

          {/* Step 3: Timetable */}
          <button
            onClick={() => navigate('/timetable')}
            className={`px-3 py-1 rounded text-xs font-mono transition-all flex items-center gap-1.5 cursor-pointer ${
              hasTimetable
                ? 'bg-[#0f172a] text-[#34d399] border border-[#059669]/40 hover:border-[#10b981]'
                : 'bg-[#1e1b4b]/60 text-[#c7d2fe] border border-[#6366f1]/40 hover:border-[#818cf8]'
            }`}
          >
            <span>{hasTimetable ? '✓' : '3.'}</span>
            <span>KAMAR Timetable</span>
          </button>
        </div>

        {/* Right: Action / Dismiss */}
        <div className="flex items-center gap-2 shrink-0">
          {!isAllComplete && (
            <button
              onClick={() => navigate('/settings')}
              className="text-xs bg-[#4fc3ff] hover:bg-[#38bdf8] text-black font-semibold px-3 py-1.5 rounded transition-all active:scale-95 cursor-pointer font-sans"
            >
              Finish Setup →
            </button>
          )}
          <button
            onClick={() => {
              setIsDismissed(true)
              localStorage.setItem('onboarding_banner_dismissed', 'true')
            }}
            title="Dismiss notification"
            className="text-[#64748b] hover:text-[#cbd5e1] p-1 text-xs transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>
      </div>
    </motion.div>
  )
}

// ─── Dashboard Page ──────────────────────────────────────────────────────────
export default function Dashboard({ defaultTab }) {
  const [bannerMsg, setBannerMsg] = useState('')
  const location = useLocation()
  const navigate = useNavigate()

  // Derive active tab from route path
  let activeTab = 'dashboard'
  if (location.pathname === '/timetable') {
    activeTab = 'timetable'
  } else if (location.pathname === '/notices') {
    activeTab = 'notices'
  } else if (defaultTab) {
    activeTab = defaultTab
  }

  const noticesRef = useRef(null)
  const mainRef = useRef(null)
  const timetableRef = useRef(null)

  useEffect(() => {
    const fetchBanner = async () => {
      try {
        const res = await fetch(`${API_URL}/api/banner`)
        if (res.ok) {
          const data = await res.json()
          setBannerMsg(data.message || '')
        }
      } catch { /* silent */ }
    }
    fetchBanner()
    const interval = setInterval(fetchBanner, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleTabClick = (tabId) => {
    navigate(`/${tabId}`)
    if (tabId === 'notices') noticesRef.current?.scrollIntoView({ behavior: 'smooth' })
    if (tabId === 'timetable') timetableRef.current?.scrollIntoView({ behavior: 'smooth' })
    if (tabId === 'dashboard') mainRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="h-screen w-full flex flex-col bg-[#000000] text-white font-sans overflow-hidden relative">
      <Navbar activeTab={activeTab} onTabClick={handleTabClick} />

      {/* Main Content */}
      <main 
        ref={mainRef}
        className="flex-1 flex flex-col relative z-10 min-h-0 overflow-hidden"
      >
        {/* Top Emergency/Admin Banner Notice (matching mirror top banner) */}
        <AnimatePresence mode="wait">
          {bannerMsg && (
            <motion.div 
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="w-full bg-[#1a0505] border-b border-[#4a1414] px-6 py-2.5 flex items-center gap-3 text-[#ffdcdc] text-sm shrink-0"
            >
              <span className="bg-[#ff4d4d] text-[#1a0000] font-bold text-[10px] uppercase tracking-wider px-2 py-0.5 rounded shrink-0 font-mono">
                NOTICE
              </span>
              <span className="truncate font-medium">{bannerMsg}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Student Onboarding Readiness Banner */}
        <StudentOnboardingBanner />

        {/* Screen Switching based on activeTab */}
        {activeTab === 'notices' && (
          <motion.div 
            key="notices-screen"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex-1 bg-[#0d0f12] overflow-y-auto min-h-0 flex flex-col"
          >
            <DailyNoticesWidget widget={{}} readonly={false} />
          </motion.div>
        )}

        {activeTab === 'timetable' && (
          <motion.div 
            key="timetable-screen"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex-1 bg-[#0d0f12] overflow-y-auto min-h-0 flex flex-col"
          >
            <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={false} />
          </motion.div>
        )}

        {activeTab === 'dashboard' && (
          <div className="grid grid-cols-1 md:grid-cols-[48%_52%] flex-1 min-h-0 overflow-hidden">
            {/* LEFT: NOTICES PANEL */}
            <motion.section 
              ref={noticesRef}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col h-full min-h-0 bg-[#000000] border-r border-[#1c1c1c]"
            >
              <DailyNoticesWidget widget={{}} readonly={true} />
            </motion.section>

            {/* RIGHT: FOCUS & CLOCK PANEL */}
            <motion.section 
              ref={timetableRef}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col p-6 md:p-8 h-full min-h-0 bg-[#000000] overflow-y-auto"
            >
              <ClockRow />
              <div className="flex-1 flex flex-col justify-center min-h-0 py-4">
                <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={true} />
              </div>
              <div className="pt-3 border-t border-[#1c1c1c] flex items-center justify-between text-[11px] font-mono text-[#666666] shrink-0 select-none">
                <div className="flex items-center gap-3">
                  <Link to="/privacy" className="hover:text-[#cbd5e1] transition-colors">
                    Privacy Policy
                  </Link>
                  <span>·</span>
                  <Link to="/terms" className="hover:text-[#cbd5e1] transition-colors">
                    Terms &amp; Conditions
                  </Link>
                </div>
                <div className="text-[10px] text-[#4fc3ff]/80 font-mono">
                  KING&apos;S HIGH SCHOOL SMART MIRROR
                </div>
              </div>
            </motion.section>
          </div>
        )}
      </main>
    </div>
  )
}
