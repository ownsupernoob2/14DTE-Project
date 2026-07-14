import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Navbar from '../components/Navbar'
import DailyNoticesWidget from '../components/DailyNoticesWidget'
import TimetableWidget from '../components/TimetableWidget'
import KingsWeekWidget from '../components/KingsWeekWidget'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// ─── Live Clock Component matching mockup ───────────────────────────────────
function Clock() {
  const [now, setNow] = useState(new Date())
  
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const hours = String(now.getHours()).padStart(2, '0')
  const minutes = String(now.getMinutes()).padStart(2, '0')
  const day = now.getDate()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const year = now.getFullYear()

  return (
    <div className="flex flex-col items-center justify-center h-full gap-2 select-none">
      <div className="font-display-lg text-[70px] md:text-[80px] leading-none font-bold text-on-surface tracking-tighter drop-shadow-[0_0_20px_rgba(173,198,255,0.35)] flex items-baseline">
        {hours}<span className="animate-pulse mx-1 text-primary/70">:</span>{minutes}
      </div>
      <div className="font-headline-md text-xs md:text-sm text-primary-fixed-dim mt-2 tracking-[0.2em] font-label-caps uppercase">
        {day} / {month} / {year}
      </div>
    </div>
  )
}

// ─── Dashboard Page ────────────────────────────────────────────────────────
export default function Dashboard() {
  const [bannerMsg, setBannerMsg] = useState('')
  const [activeTab, setActiveTab] = useState('dashboard')

  const noticesRef = useRef(null)
  const mainRef = useRef(null)
  const kingsWeekRef = useRef(null)
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

  // Smooth scroll handler for tabs
  const handleTabClick = (tabId) => {
    setActiveTab(tabId)
    
    let targetElement = null
    if (tabId === 'notices') targetElement = noticesRef.current
    if (tabId === 'kings-week') targetElement = kingsWeekRef.current
    if (tabId === 'timetable') targetElement = timetableRef.current
    
    if (targetElement) {
      targetElement.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
    } else if (tabId === 'dashboard') {
      mainRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  return (
    <div className="h-screen w-full flex flex-col bg-background text-on-background font-body-md overflow-hidden relative">
      {/* Background Ambient Glow Orbs — darker/more subtle */}
      <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden">
        <motion.div 
          animate={{
            scale: [1, 1.15, 0.95, 1],
            x: [0, 20, -10, 0],
            y: [0, -15, 25, 0],
          }}
          transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-primary rounded-full blur-[160px] opacity-[0.07]"
        />
        <motion.div 
          animate={{
            scale: [1, 0.9, 1.1, 1],
            x: [0, -25, 15, 0],
            y: [0, 20, -15, 0],
          }}
          transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
          className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-tertiary rounded-full blur-[160px] opacity-[0.07]"
        />
      </div>

      <Navbar activeTab={activeTab} onTabClick={handleTabClick} />

      {/* Main Content */}
      <main 
        ref={mainRef}
        className="flex-1 p-4 md:p-8 overflow-y-auto custom-scrollbar flex flex-col gap-6 relative z-10 min-h-0"
      >
        {/* Important Banner */}
        <AnimatePresence mode="wait">
          {bannerMsg && (
            <motion.div 
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ type: 'spring', stiffness: 260, damping: 25 }}
              className="w-full bg-error-container text-on-error-container rounded-lg p-4 flex items-center gap-4 shadow-[0_0_15px_rgba(147,0,10,0.35)] border border-error/20 shrink-0"
            >
              <span className="material-symbols-outlined fill text-error text-3xl select-none" data-icon="warning">warning</span>
              <div>
                <h2 className="font-headline-md text-base md:text-lg font-bold uppercase tracking-wide">Important Message / Notice</h2>
                <p className="font-body-md text-xs md:text-sm mt-1 opacity-90">{bannerMsg}</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Bento Grid layout */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 flex-1 min-h-[500px]">
          
          {/* Left Column: Notices — freeform, no background */}
          <motion.section 
            ref={noticesRef}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
            className="md:col-span-4 flex flex-col relative h-full min-h-[400px]"
          >
            <DailyNoticesWidget widget={{}} readonly={true} />
          </motion.section>

          {/* Middle Column: Clock (top) & Featured News (bottom) */}
          <div ref={kingsWeekRef} className="md:col-span-5 flex flex-col gap-6 h-full">
            {/* Clock Widget — no background */}
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="flex flex-col items-center justify-center p-6 relative overflow-hidden group min-h-[120px]"
            >
              <Clock />
            </motion.div>

            {/* King's Week Featured News */}
            <KingsWeekWidget />
          </div>

          {/* Right Column: Timetable — freeform, no background */}
          <motion.section 
            ref={timetableRef}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
            className="md:col-span-3 flex flex-col relative h-full min-h-[400px]"
          >
            <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={true} />
          </motion.section>

        </div>

        {/* Spacing for mobile bottom bar */}
        <div className="h-16 md:hidden shrink-0" />
      </main>

      {/* BottomNavBar (Visible on Mobile only) */}
      <nav className="md:hidden fixed bottom-0 left-0 w-full z-50 flex justify-around items-center h-16 px-4 bg-surface-container/90 backdrop-blur-md border-t border-outline-variant/40 shadow-[0_-4px_10px_rgba(0,0,0,0.15)] rounded-t-xl">
        {[
          { id: 'dashboard', label: 'Home', icon: 'home' },
          { id: 'notices', label: 'Notices', icon: 'chat_bubble' },
          { id: 'kings-week', label: 'News', icon: 'article' },
          { id: 'timetable', label: 'Schedule', icon: 'schedule' },
        ].map((tab) => {
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => handleTabClick(tab.id)}
              className={`flex flex-col items-center justify-center transition-all duration-300 ${
                isActive 
                  ? 'bg-secondary-container text-on-secondary-container rounded-full px-4 py-1.5 scale-105' 
                  : 'text-on-surface-variant hover:text-primary active:scale-95'
              }`}
            >
              <span className="material-symbols-outlined text-xl" data-icon={tab.icon}>{tab.icon}</span>
              <span className="font-label-caps text-[9px] mt-0.5 font-bold uppercase tracking-wider">{tab.label}</span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
