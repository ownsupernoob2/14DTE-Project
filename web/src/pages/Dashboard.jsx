import { useState, useEffect } from 'react'
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
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      color: 'white',
      textAlign: 'center'
    }}>
      <div style={{
        fontSize: '5rem',
        fontWeight: 'bold',
        letterSpacing: '-0.025em',
        marginBottom: '8px',
        fontFamily: 'var(--font-family)',
        textShadow: '0 4px 12px rgba(0,0,0,0.5)'
      }}>
        {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
      <div style={{
        fontSize: '1.25rem',
        fontWeight: '500',
        color: 'var(--text-secondary)',
        textShadow: '0 2px 4px rgba(0,0,0,0.3)'
      }}>
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
    <div className="dashboard-container" style={{
      overflow: 'hidden',
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      position: 'relative',
      backgroundColor: '#0a0a0f',
      padding: '0',
      margin: '0',
      boxSizing: 'border-box'
    }}>
      <Navbar />
      
      {/* Background gradients */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0 }}>
        <div style={{
          position: 'absolute',
          top: '-10%',
          left: '-10%',
          width: '40%',
          height: '40%',
          borderRadius: '50%',
          background: 'rgba(109, 40, 217, 0.1)',
          filter: 'blur(120px)'
        }} />
        <div style={{
          position: 'absolute',
          bottom: '-10%',
          right: '-10%',
          width: '40%',
          height: '40%',
          borderRadius: '50%',
          background: 'rgba(56, 189, 248, 0.1)',
          filter: 'blur(120px)'
        }} />
      </div>

      <div style={{
        flex: 1,
        padding: '24px',
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
        maxHeight: 'calc(100vh - 64px)',
        boxSizing: 'border-box'
      }}>
        
        {/* Banner Section */}
        {bannerMsg && (
          <div style={{
            width: '100%',
            backgroundColor: 'rgba(239, 68, 68, 0.2)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '12px',
            padding: '16px',
            backdropFilter: 'blur(12px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)'
          }}>
            <span style={{
              color: '#fca5a5',
              fontWeight: '600',
              fontSize: '1.125rem',
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <svg style={{ width: '24px', height: '24px', color: '#f87171' }} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
              {bannerMsg}
            </span>
          </div>
        )}

        {/* Main 3-Column Layout */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'row',
          gap: '24px',
          minHeight: 0,
          width: '100%',
          boxSizing: 'border-box'
        }}>
          
          {/* Left Column: Notices */}
          <div style={{
            width: '25%',
            height: '100%',
            borderRadius: '16px',
            overflow: 'hidden',
            backgroundColor: 'var(--glass-bg)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            boxSizing: 'border-box'
          }}>
            <DailyNoticesWidget widget={{}} readonly={true} />
          </div>
          
          {/* Center Column: Clock + Kings Week */}
          <div style={{
            width: '50%',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            gap: '24px',
            minHeight: 0,
            boxSizing: 'border-box'
          }}>
            <div style={{
              flex: 1,
              borderRadius: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '32px'
            }}>
              <Clock />
            </div>
            
            <div style={{
              height: '45%',
              borderRadius: '16px',
              overflow: 'hidden',
              boxSizing: 'border-box'
            }}>
              <KingsWeekWidget />
            </div>
          </div>
          
          {/* Right Column: Timetable */}
          <div style={{
            width: '25%',
            height: '100%',
            borderRadius: '16px',
            overflow: 'hidden',
            backgroundColor: 'var(--glass-bg)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            boxSizing: 'border-box'
          }}>
            <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={true} />
          </div>
          
        </div>
      </div>
    </div>
  )
}
