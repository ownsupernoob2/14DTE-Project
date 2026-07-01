import { useState } from 'react'
import BarcodeScannerComponent from 'react-qr-barcode-scanner'

export default function QRScanner() {
  const [data, setData] = useState('No result yet')
  const [error, setError] = useState(null)
  const [stopStream, setStopStream] = useState(false)

  function handleUpdate(err, result) {
    if (result) {
      console.log('QR/Barcode scanned:', result)
      console.log('Raw text:', result?.text)
      setData(result.text)
      setError(null)
    } else if (err) {
      // err fires constantly when no code is in view — only log real errors
      if (err?.name !== 'NotFoundException') {
        console.error('Scanner error:', err)
        setError(err?.message || 'Unknown error')
      }
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: "'Inter', sans-serif",
      color: '#e2e8f0',
      padding: '2rem',
      gap: '2rem',
    }}>
      <h1 style={{
        fontSize: '2rem',
        fontWeight: 700,
        background: 'linear-gradient(90deg, #818cf8, #c084fc)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        margin: 0,
      }}>
        QR / Barcode Scanner
      </h1>

      <p style={{ color: '#94a3b8', margin: 0, fontSize: '0.95rem' }}>
        Point your camera at a QR code or barcode — results are logged to the console.
      </p>

      {/* Scanner viewport */}
      <div style={{
        borderRadius: '16px',
        overflow: 'hidden',
        boxShadow: '0 0 40px rgba(129,140,248,0.3)',
        border: '2px solid rgba(129,140,248,0.4)',
        width: '100%',
        maxWidth: '420px',
      }}>
        <BarcodeScannerComponent
          width="100%"
          height={320}
          onUpdate={handleUpdate}
          stopStream={stopStream}
        />
      </div>

      {/* Result card */}
      <div style={{
        background: 'rgba(255,255,255,0.05)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: '12px',
        padding: '1.5rem 2rem',
        width: '100%',
        maxWidth: '420px',
        textAlign: 'center',
      }}>
        <p style={{ margin: '0 0 0.5rem', color: '#94a3b8', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Last Scanned Value
        </p>
        <p style={{
          margin: 0,
          fontSize: '1.1rem',
          fontWeight: 600,
          color: data === 'No result yet' ? '#64748b' : '#a5f3fc',
          wordBreak: 'break-all',
        }}>
          {data}
        </p>
        {error && (
          <p style={{ margin: '0.75rem 0 0', color: '#f87171', fontSize: '0.85rem' }}>
            {error}
          </p>
        )}
      </div>

      {/* Stop / Resume toggle */}
      <button
        onClick={() => setStopStream(s => !s)}
        style={{
          padding: '0.65rem 2rem',
          borderRadius: '8px',
          border: 'none',
          cursor: 'pointer',
          fontWeight: 600,
          fontSize: '0.95rem',
          background: stopStream
            ? 'linear-gradient(90deg, #818cf8, #c084fc)'
            : 'rgba(239,68,68,0.15)',
          color: stopStream ? '#fff' : '#f87171',
          border: stopStream ? 'none' : '1px solid rgba(239,68,68,0.4)',
          transition: 'all 0.2s',
        }}
      >
        {stopStream ? 'Resume Camera' : 'Stop Camera'}
      </button>
    </div>
  )
}
