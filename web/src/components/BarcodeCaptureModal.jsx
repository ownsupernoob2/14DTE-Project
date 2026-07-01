import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import BarcodeScannerComponent from 'react-qr-barcode-scanner'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

export default function BarcodeCaptureModal({ isOpen, onClose, onBarcodeSaved }) {
  const { getAccessTokenSilently } = useAuth0()

  const [phase, setPhase] = useState('scan') // 'scan' | 'saving' | 'success' | 'error'
  const [errorMsg, setErrorMsg] = useState('')
  const [decodedCode, setDecodedCode] = useState('')
  const [stopStream, setStopStream] = useState(false)

  // Prevent double-fires while we await the server
  const handledRef = useRef(false)

  // Reset everything when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setPhase('scan')
      setDecodedCode('')
      setErrorMsg('')
      setStopStream(false)
      handledRef.current = false
    } else {
      setStopStream(true)
    }
  }, [isOpen])

  // Save to server
  const saveBarcodeToServer = async (code) => {
    setPhase('saving')
    console.log('Barcode scanned, sending to server:', code)
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/users/me/barcode`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ barcode: code })
      })

      console.log('Server response status:', res.status)
      const body = await res.json().catch(() => ({}))
      console.log('Server response body:', body)

      if (res.ok) {
        setDecodedCode(code)
        setPhase('success')
        onBarcodeSaved?.(code)
      } else {
        setErrorMsg(body?.detail || body?.message || 'Failed to attach barcode. Please try again.')
        setPhase('error')
      }
    } catch (err) {
      console.error('Barcode save error:', err)
      setErrorMsg('Network error. Check server connectivity.')
      setPhase('error')
    }
  }

  // Called by BarcodeScannerComponent on every frame
  const handleUpdate = (err, result) => {
    if (result && phase === 'scan' && !handledRef.current) {
      handledRef.current = true
      setStopStream(true)

      const code = result.text
      console.log('react-qr-barcode-scanner result object:', result)
      console.log('Decoded barcode text:', code)

      // Beep feedback
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
        const osc = audioCtx.createOscillator()
        const gain = audioCtx.createGain()
        osc.connect(gain)
        gain.connect(audioCtx.destination)
        osc.frequency.setValueAtTime(1200, audioCtx.currentTime)
        gain.gain.setValueAtTime(0.08, audioCtx.currentTime)
        osc.start()
        osc.stop(audioCtx.currentTime + 0.1)
      } catch (_) { /* ignore */ }

      saveBarcodeToServer(code)
    }
  }

  const handleClose = () => {
    setStopStream(true)
    onClose()
  }

  if (!isOpen) return null

  return (
    <AnimatePresence>
      <motion.div
        className="fc-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={(e) => e.target === e.currentTarget && phase !== 'saving' && handleClose()}
      >
        <motion.div
          className="fc-modal"
          initial={{ opacity: 0, scale: 0.95, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 16 }}
          transition={{ duration: 0.25 }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close button */}
          {phase !== 'saving' && (
            <button className="fc-close" onClick={handleClose} aria-label="Close modal">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}

          <AnimatePresence mode="wait">

            {/* SCAN PHASE */}
            {phase === 'scan' && (
              <motion.div
                key="scan"
                className="fc-phase fc-phase-capture"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <p className="fc-overline">Camera Scanner</p>
                <h2 className="fc-title">Scan Student Barcode</h2>
                <p className="fc-sub" style={{ marginBottom: '8px' }}>
                  Hold your barcode card in front of the camera to scan.
                </p>

                {/* Scanner viewport */}
                <div
                  className="fc-cam-box"
                  style={{
                    width: '320px', height: '240px',
                    borderRadius: '16px', overflow: 'hidden',
                    position: 'relative', background: '#000'
                  }}
                >
                  <BarcodeScannerComponent
                    width={320}
                    height={240}
                    onUpdate={handleUpdate}
                    stopStream={stopStream}
                  />

                  {/* Targeting overlay */}
                  <div style={{
                    position: 'absolute',
                    top: '50%', left: '50%',
                    transform: 'translate(-50%, -50%)',
                    width: '260px', height: '100px',
                    border: '2px dashed var(--accent)',
                    boxShadow: '0 0 0 9999px rgba(0,0,0,0.4)',
                    borderRadius: '8px',
                    pointerEvents: 'none'
                  }} />
                </div>

                <div className="fc-row-btns" style={{ marginTop: '16px' }}>
                  <motion.button
                    className="fc-btn fc-btn-outline"
                    whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                    onClick={handleClose}
                  >
                    Cancel
                  </motion.button>
                </div>
              </motion.div>
            )}

            {/* SAVING PHASE */}
            {phase === 'saving' && (
              <motion.div key="saving" className="fc-phase fc-phase-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                <div className="fc-pulse-ring" />
                <h2 className="fc-title">Attaching Barcode</h2>
                <p className="fc-sub">Linking barcode to your mirror layout...</p>
              </motion.div>
            )}

            {/* SUCCESS PHASE */}
            {phase === 'success' && (
              <motion.div key="success" className="fc-phase fc-phase-center" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <div className="fc-status-ring fc-status-ok">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M7 16l7 7 11-11" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h2 className="fc-title">Barcode Attached</h2>
                <p className="fc-sub">
                  Successfully registered barcode <strong>{decodedCode}</strong>. You can now use this barcode to identify yourself at the mirror.
                </p>
                <motion.button className="fc-btn" style={{ marginTop: '16px' }} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleClose}>
                  Done
                </motion.button>
              </motion.div>
            )}

            {/* ERROR PHASE */}
            {phase === 'error' && (
              <motion.div key="error" className="fc-phase fc-phase-center" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <div className="fc-status-ring fc-status-err">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M10 10l12 12M22 10L10 22" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                  </svg>
                </div>
                <h2 className="fc-title">Scan Failed</h2>
                <p className="fc-sub" style={{ color: 'rgba(255,255,255,0.5)' }}>{errorMsg}</p>
                <div className="fc-row-btns" style={{ marginTop: '24px' }}>
                  <motion.button className="fc-btn fc-btn-outline" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleClose}>Cancel</motion.button>
                  <motion.button className="fc-btn" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={() => { handledRef.current = false; setStopStream(false); setPhase('scan') }}>Try Again</motion.button>
                </div>
              </motion.div>
            )}

          </AnimatePresence>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
