import { useState, useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import Navbar from '../components/Navbar'
import DailyNoticesWidget from '../components/DailyNoticesWidget'
import TimetableWidget from '../components/TimetableWidget'
import KingsWeekWidget from '../components/KingsWeekWidget'
import { useServerStatus } from '../contexts/ServerStatusContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

function Clock() {
  const [now, setNow] = useState(new Date())
  
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  
  return (
    <div className="flex flex-col items-center justify-center h-full text-white">
      <div className="text-8xl font-bold tracking-tight mb-2 drop-shadow-lg" style={{ fontFamily: 'var(--font-family)' }}>
        {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
      <div className="text-2xl font-medium text-[var(--text-secondary)]">
        {now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [bannerMsg, setBannerMsg] = useState('')
  const { isServerUp } = useServerStatus()

  useEffect(() => {
    const fetchBanner = async () => {
      try {
        const res = await fetch(`${API_URL}/api/banner`)
        if (res.ok) {
          const data = await res.json()
          setBannerMsg(data.message || '')
        }
      } catch (e) {
        console.error('Failed to fetch banner:', e)
      }
    }
    
    fetchBanner()
    const interval = setInterval(fetchBanner, 60000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="dashboard-container overflow-hidden h-screen flex flex-col relative bg-[#0a0a0f]">
      <Navbar />
      
      {/* Background gradients */}
      <div className="absolute inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-purple-600/10 blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-blue-600/10 blur-[120px]" />
      </div>

      <div className="flex-1 p-6 z-10 flex flex-col gap-6 max-h-[calc(100vh-64px)]">
        
        {/* Banner Section */}
        {bannerMsg && (
          <div className="w-full bg-red-500/20 border border-red-500/30 rounded-xl p-4 backdrop-blur-md flex items-center justify-center shadow-lg">
            <span className="text-red-200 font-semibold text-lg tracking-wide uppercase flex items-center gap-2">
              <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
              {bannerMsg}
            </span>
          </div>
        )}

        {/* Main 3-Column Layout */}
        <div className="flex-1 grid grid-cols-12 gap-6 min-h-0">
          
          {/* Left Column: Notices */}
          <div className="col-span-3 h-full rounded-2xl overflow-hidden glass-panel border border-white/5">
            <DailyNoticesWidget widget={{}} readonly={true} />
          </div>
          
          {/* Center Column: Clock + Kings Week */}
          <div className="col-span-6 h-full flex flex-col gap-6 min-h-0">
            <div className="flex-1 rounded-2xl flex items-center justify-center p-8">
              <Clock />
            </div>
            
            <div className="h-[45%] rounded-2xl">
              <KingsWeekWidget />
            </div>
          </div>
          
          {/* Right Column: Timetable */}
          <div className="col-span-3 h-full rounded-2xl overflow-hidden glass-panel border border-white/5">
            <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={true} />
          </div>
          
        </div>
      </div>
    </div>
  )
}
