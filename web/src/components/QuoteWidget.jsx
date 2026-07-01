import { useEffect, useState } from 'react'

const SCHOOL_QUOTES = [
  "Focus on progress, not perfection.",
  "Your future is created by what you do today, not tomorrow.",
  "Mistakes are proof that you are trying.",
  "Believe you can and you're halfway there.",
  "Every expert was once a beginner.",
  "Success is the sum of small efforts, repeated day in and day out.",
  "The only way to learn mathematics is to do mathematics.",
  "Strive for progress, not perfection.",
  "The secret of getting ahead is getting started."
]

export default function QuoteWidget({ readonly = false }) {
  const [quote, setQuote] = useState("")

  useEffect(() => {
    // Generate a quote based on the current day so it changes daily but stays consistent during sessions
    const day = new Date().getDate()
    setQuote(SCHOOL_QUOTES[day % SCHOOL_QUOTES.length])
  }, [])

  return (
    <div className="widget-quote" style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100%',
      padding: '16px',
      textAlign: 'center'
    }}>
      <p style={{
        fontStyle: 'italic',
        fontSize: '1.25em',
        color: '#e2e8f0',
        lineHeight: 1.5,
        margin: 0
      }}>
        "{quote}"
      </p>
      <span style={{
        marginTop: '8px',
        fontSize: '0.8em',
        color: 'rgba(255,255,255,0.4)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em'
      }}>
        Daily Motivation
      </span>
    </div>
  )
}
