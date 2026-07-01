import { useState, useEffect } from 'react'

export default function CountdownWidget() {
  const [timeLeft, setTimeLeft] = useState("")

  useEffect(() => {
    const updateCountdown = () => {
      const now = new Date()
      // Let's set a target end of school day at 3:00 PM today
      const target = new Date()
      target.setHours(15, 0, 0, 0)

      if (now > target) {
        // School is over, show countdown to tomorrow's start 8:45 AM
        const tomorrow = new Date()
        tomorrow.setDate(tomorrow.getDate() + 1)
        tomorrow.setHours(8, 45, 0, 0)
        
        const diff = tomorrow - now
        const hrs = Math.floor(diff / 3600000)
        const mins = Math.floor((diff % 3600000) / 60000)
        setTimeLeft(`School starts in ${hrs}h ${mins}m`)
      } else {
        const diff = target - now
        const hrs = Math.floor(diff / 3600000)
        const mins = Math.floor((diff % 3600000) / 60000)
        const secs = Math.floor((diff % 60000) / 1000)
        setTimeLeft(`${hrs}h ${mins}m ${secs}s left in school day`)
      }
    }

    updateCountdown()
    const interval = setInterval(updateCountdown, 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="widget-countdown" style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100%',
      padding: '16px',
      textAlign: 'center'
    }}>
      <div style={{
        fontSize: '1.2em',
        fontWeight: 'bold',
        color: '#38bdf8',
        letterSpacing: '0.02em',
        marginBottom: '6px'
      }}>
        {timeLeft}
      </div>
      <span style={{
        fontSize: '0.75em',
        color: 'rgba(255,255,255,0.4)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em'
      }}>
        School Day Timer
      </span>
    </div>
  )
}
