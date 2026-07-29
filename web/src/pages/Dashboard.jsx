import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Navbar from '../components/Navbar'
import DailyNoticesWidget from '../components/DailyNoticesWidget'
import TimetableWidget from '../components/TimetableWidget'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// ─── Live Clock Header Row matching new-style ─────────────────────────────
function ClockRow() {
  const [now, setNow] = useState(new Date())
  
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const hours = String(now.getHours()).padStart(2, '0')
  const minutes = String(now.getMinutes()).padStart(2, '0')
  const dateStr = now.toLocaleDateString('en-NZ', { weekday: 'short', day: 'numeric', month: 'short' })

  return (
    <div className="flex justify-between items-baseline font-mono pb-5 border-b border-[#1c1c1c] w-full select-none">
      <span className="text-[18px] text-[#d0d0d0]">{dateStr}</span>
      <span className="text-[44px] md:text-[48px] font-semibold text-white tracking-tight">{hours}:{minutes}</span>
    </div>
  )
}

// ─── Dashboard Page ────────────────────────────────────────────────────────
export default function Dashboard() {
  const [bannerMsg, setBannerMsg] = useState('')
  const [activeTab, setActiveTab] = useState('dashboard')

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
    const interval = setInterval(fetchBanner, 60000)
    return () => clearInterval(interval)
  }, [])

  const handleTabClick = (tabId) => {
    setActiveTab(tabId)
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
        {/* Top Banner Notice (matching new-style.html) */}
        <AnimatePresence mode="wait">
          {bannerMsg && (
            <motion.div 
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="w-full bg-gradient-to-r from-[#3a0d0d] to-[#1a0505] border-b border-[#4a1414] px-6 py-3 flex items-center gap-3 text-[#ffdcdc] text-sm shrink-0"
            >
              <span className="bg-[#ff4d4d] text-[#1a0000] font-bold text-[11px] uppercase tracking-wider px-2 py-0.5 rounded shrink-0">
                Notice
              </span>
              <span className="truncate">{bannerMsg}</span>
            </motion.div>
          )}
        </AnimatePresence>

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

        {(activeTab === 'dashboard' || (activeTab !== 'notices' && activeTab !== 'timetable')) && (
          <div className="grid grid-cols-1 md:grid-cols-[48%_52%] flex-1 min-h-0 overflow-hidden">
            {/* LEFT: NOTICES PANEL */}
            <motion.section 
              ref={noticesRef}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4 }}
              className="flex flex-col h-full min-h-0 bg-[#000000]"
            >
              <DailyNoticesWidget widget={{}} readonly={true} />
            </motion.section>

            {/* RIGHT: FOCUS & CLOCK PANEL */}
            <motion.section 
              ref={timetableRef}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4 }}
              className="flex flex-col p-6 md:p-8 h-full min-h-0 bg-[#000000] overflow-y-auto"
            >
              <ClockRow />
              <div className="flex-1 flex flex-col justify-center min-h-0 py-4">
                <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={true} />
              </div>
            </motion.section>
          </div>
        )}
      </main>
    </div>
  )
}

