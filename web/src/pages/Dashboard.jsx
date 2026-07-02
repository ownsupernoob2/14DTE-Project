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
        fontSize: '5.5rem',
        fontWeight: 'bold',
        letterSpacing: '-0.02em',
        marginBottom: '6px',
        fontFamily: 'var(--font-family)',
        textShadow: '0 4px 16px rgba(0,0,0,0.6)'
      }}>
        {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
      <div style={{
        fontSize: '1.35rem',
        fontWeight: '500',
        color: 'var(--text-secondary)',
        opacity: 0.85
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
      backgroundColor: '#050508',
      padding: '0',
      margin: '0',
      boxSizing: 'border-box'
    }}>
      <Navbar />
      
      {/* Background radial gradients for dynamic look under the glass panel */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0 }}>
        <div style={{
          position: 'absolute',
          top: '-15%',
          left: '-15%',
          width: '50%',
          height: '50%',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(124, 58, 237, 0.15) 0%, rgba(124, 58, 237, 0) 70%)',
          filter: 'blur(100px)'
        }} />
        <div style={{
          position: 'absolute',
          bottom: '-15%',
          right: '-15%',
          width: '50%',
          height: '50%',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(14, 165, 233, 0.15) 0%, rgba(14, 165, 233, 0) 70%)',
          filter: 'blur(100px)'
        }} />
      </div>

      <div style={{
        flex: 1,
        padding: '24px 32px 32px',
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        maxHeight: 'calc(100vh - 64px)',
        boxSizing: 'border-box'
      }}>
        
        {/* Banner Section */}
        {bannerMsg && (
          <div style={{
            width: '100%',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: '16px',
            padding: '14px',
            backdropFilter: 'blur(20px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 8px 32px rgba(239, 68, 68, 0.1)'
          }}>
            <span style={{
              color: '#fecaca',
              fontWeight: '600',
              fontSize: '1rem',
              letterSpacing: '0.075em',
              textTransform: 'uppercase',
              display: 'flex',
              alignItems: 'center',
              gap: '10px'
            }}>
              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#ef4444', animate: 'pulse 2s infinite' }} />
              {bannerMsg}
            </span>
          </div>
        )}

        {/* Master Connected Glass Deck */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'row',
          minHeight: 0,
          width: '100%',
          borderRadius: '24px',
          backgroundColor: 'rgba(15, 15, 25, 0.45)',
          backdropFilter: 'blur(30px)',
          WebkitBackdropFilter: 'blur(30px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          boxShadow: '0 24px 60px rgba(0, 0, 0, 0.6), inset 0 1px 1px rgba(255, 255, 255, 0.1)',
          boxSizing: 'border-box',
          overflow: 'hidden'
        }}>
          
          {/* Left Column: Notices */}
          <div style={{
            width: '26%',
            height: '100%',
            borderRight: '1px solid rgba(255, 255, 255, 0.08)',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <DailyNoticesWidget widget={{}} readonly={true} />
          </div>
          
          {/* Center Column: Clock (Top) & Kings Week (Bottom) */}
          <div style={{
            width: '48%',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box'
          }}>
            {/* Clock area */}
            <div style={{
              flex: '1.2',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '24px',
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)'
            }}>
              <Clock />
            </div>
            
            {/* Kings Week area */}
            <div style={{
              flex: '1',
              padding: '20px',
              boxSizing: 'border-box',
              display: 'flex',
              alignItems: 'stretch'
            }}>
              <div style={{ flex: 1, borderRadius: '16px', overflow: 'hidden' }}>
                <KingsWeekWidget />
              </div>
            </div>
          </div>
          
          {/* Right Column: Timetable */}
          <div style={{
            width: '26%',
            height: '100%',
            borderLeft: '1px solid rgba(255, 255, 255, 0.08)',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={true} />
          </div>
          
        </div>
      </div>
    </div>
  )
}
