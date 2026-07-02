import { useState, useEffect, useRef } from 'react'
import Navbar from '../components/Navbar'
import DailyNoticesWidget from '../components/DailyNoticesWidget'
import TimetableWidget from '../components/TimetableWidget'
import KingsWeekWidget from '../components/KingsWeekWidget'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// ─── Live Clock ──────────────────────────────────────────────────────────────
function Clock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const timeStr = now.toLocaleTimeString('en-NZ', { hour: '2-digit', minute: '2-digit', hour12: true })
  const dateStr = now.toLocaleDateString('en-NZ', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      gap: '8px',
    }}>
      <div style={{
        fontSize: 'clamp(3rem, 6vw, 5.5rem)',
        fontWeight: '200',
        letterSpacing: '-0.03em',
        color: '#ffffff',
        fontFamily: "'Inter', sans-serif",
        lineHeight: 1,
        textShadow: '0 2px 40px rgba(255,255,255,0.15)',
      }}>
        {timeStr}
      </div>
      <div style={{
        fontSize: 'clamp(0.85rem, 1.2vw, 1.1rem)',
        fontWeight: '400',
        color: 'rgba(255,255,255,0.5)',
        letterSpacing: '0.05em',
        fontFamily: "'Inter', sans-serif",
      }}>
        {dateStr}
      </div>
    </div>
  )
}

// ─── Divider ─────────────────────────────────────────────────────────────────
function VDivider() {
  return <div style={{ width: '1px', background: 'rgba(255,255,255,0.07)', flexShrink: 0 }} />
}
function HDivider() {
  return <div style={{ height: '1px', background: 'rgba(255,255,255,0.07)', flexShrink: 0 }} />
}

// ─── Dashboard ───────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [bannerMsg, setBannerMsg] = useState('')

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

  return (
    <div style={{
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      background: '#050508',
      overflow: 'hidden',
      position: 'relative',
      fontFamily: "'Inter', sans-serif",
    }}>
      {/* Ambient background orbs */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0 }}>
        <div style={{
          position: 'absolute', top: '-20%', left: '-10%',
          width: '55%', height: '55%', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(109,40,217,0.18) 0%, transparent 70%)',
          filter: 'blur(80px)',
        }} />
        <div style={{
          position: 'absolute', bottom: '-20%', right: '-10%',
          width: '55%', height: '55%', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(14,165,233,0.15) 0%, transparent 70%)',
          filter: 'blur(80px)',
        }} />
      </div>

      <Navbar style={{ position: 'relative', zIndex: 10 }} />

      {/* Main body — below navbar */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        padding: '0 20px 20px 20px',
        gap: '12px',
        minHeight: 0,
        zIndex: 5,
        boxSizing: 'border-box',
      }}>

        {/* ── Important Banner (always shown — dimmed if empty) ── */}
        <div style={{
          width: '100%',
          padding: '10px 20px',
          borderRadius: '14px',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          background: bannerMsg
            ? 'rgba(239,68,68,0.12)'
            : 'rgba(255,255,255,0.03)',
          border: bannerMsg
            ? '1px solid rgba(239,68,68,0.3)'
            : '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '10px',
          transition: 'all 0.4s ease',
          flexShrink: 0,
          minHeight: '42px',
        }}>
          {bannerMsg ? (
            <>
              <span style={{
                width: '7px', height: '7px', borderRadius: '50%',
                background: '#ef4444', flexShrink: 0,
                boxShadow: '0 0 8px #ef4444',
                animation: 'pulse 2s infinite',
              }} />
              <span style={{
                color: '#fecaca',
                fontWeight: '600',
                fontSize: '0.9rem',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
              }}>
                {bannerMsg}
              </span>
            </>
          ) : (
            <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.75rem', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
              Important Messages &amp; Announcements
            </span>
          )}
        </div>

        {/* ── Master glass deck: 3 columns ── */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'row',
          minHeight: 0,
          borderRadius: '20px',
          background: 'rgba(12,12,20,0.55)',
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          border: '1px solid rgba(255,255,255,0.07)',
          boxShadow: '0 20px 60px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.06)',
          overflow: 'hidden',
        }}>

          {/* ── LEFT: Notices ── */}
          <div style={{
            width: '26%',
            minWidth: '220px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            <DailyNoticesWidget widget={{}} readonly={true} />
          </div>

          <VDivider />

          {/* ── CENTER: Clock (top) + Kings Week (bottom) ── */}
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
          }}>
            {/* Clock */}
            <div style={{
              flex: '1.1',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '24px',
            }}>
              <Clock />
            </div>

            <HDivider />

            {/* Kings Week */}
            <div style={{
              flex: '1',
              padding: '16px',
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
            }}>
              <KingsWeekWidget />
            </div>
          </div>

          <VDivider />

          {/* ── RIGHT: Timetable ── */}
          <div style={{
            width: '26%',
            minWidth: '220px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            <TimetableWidget widget={{ data: { viewMode: 'today' } }} readonly={true} />
          </div>

        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}
