import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import BarcodeScannerComponent from 'react-qr-barcode-scanner'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// Mirrors validateBarcode/normalizeBarcode in server/handlers_barcode.go so the
// student sees the same verdict here that the server would give.
const ID_MIN = 4
const ID_MAX = 32
const ID_SHAPE = /^[A-Z0-9][A-Z0-9-]*$/

export function normalizeStudentID(raw) {
  return (raw || '').replace(/\s+/g, '').toUpperCase()
}

export function validateStudentID(code) {
  if (code.length < ID_MIN) return `Student ID must be at least ${ID_MIN} characters.`
  if (code.length > ID_MAX) return `Student ID must be at most ${ID_MAX} characters.`
  if (!ID_SHAPE.test(code)) return 'Student ID may only contain letters, numbers and dashes.'
  return null
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.setValueAtTime(1200, ctx.currentTime)
    gain.gain.setValueAtTime(0.08, ctx.currentTime)
    osc.start()
    osc.stop(ctx.currentTime + 0.1)
  } catch {
    // Audio feedback is a nicety; a blocked AudioContext must not break the scan.
  }
}

export default function BarcodeCaptureModal({ isOpen, onClose, onBarcodeSaved }) {
  const { getAccessTokenSilently } = useAuth0()

  const [phase, setPhase] = useState('input')   // 'input' | 'saving' | 'success' | 'error'
  const [mode, setMode] = useState('scan')      // 'scan' | 'manual'
  const [errorMsg, setErrorMsg] = useState('')
  const [savedCode, setSavedCode] = useState('')
  const [manualCode, setManualCode] = useState('')
  const [stopStream, setStopStream] = useState(false)

  // Guards the camera path: onUpdate fires per frame and would double-submit.
  const handledRef = useRef(false)

  useEffect(() => {
    if (isOpen) {
      setPhase('input')
      setMode('scan')
      setSavedCode('')
      setManualCode('')
      setErrorMsg('')
      setStopStream(false)
      handledRef.current = false
    } else {
      setStopStream(true)
    }
  }, [isOpen])

  // Releasing the camera when the student switches to typing avoids holding the
  // webcam open behind a form they are no longer looking at.
  const switchMode = (next) => {
    setMode(next)
    setStopStream(next !== 'scan')
    if (next === 'scan') handledRef.current = false
    setErrorMsg('')
  }

  const linkStudentID = async (rawCode) => {
    const code = normalizeStudentID(rawCode)
    const invalid = validateStudentID(code)
    if (invalid) {
      setErrorMsg(invalid)
      setPhase('error')
      return
    }

    setPhase('saving')
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/users/me/barcode`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ barcode: code }),
      })
      const body = await res.json().catch(() => ({}))

      if (res.ok) {
        setSavedCode(body.barcode || code)
        setPhase('success')
        onBarcodeSaved?.(body.barcode || code)
      } else {
        setErrorMsg(body?.error || body?.message || 'Could not link that student ID. Please try again.')
        setPhase('error')
      }
    } catch {
      setErrorMsg('Network error. Check that the server is reachable.')
      setPhase('error')
    }
  }

  const handleScan = (err, result) => {
    if (!result || phase !== 'input' || mode !== 'scan' || handledRef.current) return
    handledRef.current = true
    setStopStream(true)
    beep()
    linkStudentID(result.text)
  }

  const handleClose = () => {
    setStopStream(true)
    onClose()
  }

  const retry = () => {
    handledRef.current = false
    setErrorMsg('')
    setStopStream(mode !== 'scan')
    setPhase('input')
  }

  if (!isOpen) return null

  const manualNormalized = normalizeStudentID(manualCode)
  const manualError = manualNormalized ? validateStudentID(manualNormalized) : null
  const canSubmitManual = manualNormalized.length > 0 && !manualError

  const tabStyle = (active) => ({
    flex: 1,
    padding: '9px 12px',
    fontSize: '0.8rem',
    fontWeight: 600,
    letterSpacing: '0.04em',
    borderRadius: '8px',
    border: `1px solid ${active ? 'var(--accent, #60a5fa)' : 'rgba(255,255,255,0.12)'}`,
    background: active ? 'rgba(96,165,250,0.14)' : 'transparent',
    color: active ? 'var(--accent, #60a5fa)' : 'rgba(255,255,255,0.6)',
    cursor: 'pointer',
    transition: 'all 0.18s ease',
  })

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
          {phase !== 'saving' && (
            <button className="fc-close" onClick={handleClose} aria-label="Close">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}

          <AnimatePresence mode="wait">

            {/* ── INPUT: scan or type ─────────────────────────────────────── */}
            {phase === 'input' && (
              <motion.div
                key="input"
                className="fc-phase fc-phase-capture"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <p className="fc-overline">Mirror Sign-In</p>
                <h2 className="fc-title">Link Your Student ID</h2>
                <p className="fc-sub" style={{ marginBottom: '14px' }}>
                  Scan the barcode on your student ID card, or type the number by hand.
                </p>

                <div role="tablist" style={{ display: 'flex', gap: '8px', width: '100%', marginBottom: '14px' }}>
                  <button
                    role="tab"
                    aria-selected={mode === 'scan'}
                    style={tabStyle(mode === 'scan')}
                    onClick={() => switchMode('scan')}
                  >
                    Scan barcode
                  </button>
                  <button
                    role="tab"
                    aria-selected={mode === 'manual'}
                    style={tabStyle(mode === 'manual')}
                    onClick={() => switchMode('manual')}
                  >
                    Type ID
                  </button>
                </div>

                {mode === 'scan' ? (
                  <>
                    <div style={{
                      width: '320px', height: '240px', borderRadius: '16px',
                      overflow: 'hidden', position: 'relative', background: '#000',
                    }}>
                      <BarcodeScannerComponent
                        width={320}
                        height={240}
                        onUpdate={handleScan}
                        stopStream={stopStream}
                      />
                      <div style={{
                        position: 'absolute', top: '50%', left: '50%',
                        transform: 'translate(-50%, -50%)',
                        width: '260px', height: '100px',
                        border: '2px dashed var(--accent, #60a5fa)',
                        boxShadow: '0 0 0 9999px rgba(0,0,0,0.4)',
                        borderRadius: '8px', pointerEvents: 'none',
                      }} />
                    </div>
                    <p className="fc-sub" style={{ fontSize: '0.78rem', marginTop: '10px', opacity: 0.6 }}>
                      Hold the barcode flat inside the frame. Camera not working? Use “Type ID”.
                    </p>
                  </>
                ) : (
                  <form
                    style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '8px' }}
                    onSubmit={(e) => { e.preventDefault(); if (canSubmitManual) linkStudentID(manualCode) }}
                  >
                    <label
                      htmlFor="student-id-input"
                      style={{ fontSize: '0.75rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.5)' }}
                    >
                      Student ID number
                    </label>
                    <input
                      id="student-id-input"
                      type="text"
                      inputMode="text"
                      autoComplete="off"
                      autoFocus
                      value={manualCode}
                      maxLength={ID_MAX + 8}
                      onChange={(e) => setManualCode(e.target.value)}
                      placeholder="e.g. 18234"
                      style={{
                        width: '100%', padding: '12px 14px',
                        background: 'rgba(255,255,255,0.04)',
                        border: `1px solid ${manualError ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.12)'}`,
                        borderRadius: '10px', color: '#fff',
                        fontSize: '1.05rem', letterSpacing: '0.14em',
                        fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace',
                        outline: 'none',
                      }}
                    />
                    <div style={{ minHeight: '18px', fontSize: '0.76rem' }}>
                      {manualError
                        ? <span style={{ color: '#f87171' }}>{manualError}</span>
                        : manualNormalized
                          ? <span style={{ color: 'rgba(255,255,255,0.45)' }}>Will be saved as <strong>{manualNormalized}</strong></span>
                          : null}
                    </div>
                    <button
                      type="submit"
                      className="fc-btn"
                      disabled={!canSubmitManual}
                      style={{ opacity: canSubmitManual ? 1 : 0.45, cursor: canSubmitManual ? 'pointer' : 'not-allowed' }}
                    >
                      Link this ID
                    </button>
                  </form>
                )}

                <div className="fc-row-btns" style={{ marginTop: '14px' }}>
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

            {/* ── SAVING ──────────────────────────────────────────────────── */}
            {phase === 'saving' && (
              <motion.div key="saving" className="fc-phase fc-phase-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                <div className="fc-pulse-ring" />
                <h2 className="fc-title">Linking Student ID</h2>
                <p className="fc-sub">Attaching this ID to your mirror layout…</p>
              </motion.div>
            )}

            {/* ── SUCCESS ─────────────────────────────────────────────────── */}
            {phase === 'success' && (
              <motion.div key="success" className="fc-phase fc-phase-center" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <div className="fc-status-ring fc-status-ok">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M7 16l7 7 11-11" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h2 className="fc-title">Student ID Linked</h2>
                <p className="fc-sub">
                  <strong style={{ fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace', letterSpacing: '0.12em' }}>{savedCode}</strong>
                  <br />Scan this card at the mirror and it will sign you in.
                </p>
                <motion.button className="fc-btn" style={{ marginTop: '16px' }} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleClose}>
                  Done
                </motion.button>
              </motion.div>
            )}

            {/* ── ERROR ───────────────────────────────────────────────────── */}
            {phase === 'error' && (
              <motion.div key="error" className="fc-phase fc-phase-center" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <div className="fc-status-ring fc-status-err">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M10 10l12 12M22 10L10 22" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                  </svg>
                </div>
                <h2 className="fc-title">Could Not Link ID</h2>
                <p className="fc-sub" style={{ color: 'rgba(255,255,255,0.5)' }}>{errorMsg}</p>
                <div className="fc-row-btns" style={{ marginTop: '24px' }}>
                  <motion.button className="fc-btn fc-btn-outline" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleClose}>Cancel</motion.button>
                  <motion.button className="fc-btn" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={retry}>Try Again</motion.button>
                </div>
              </motion.div>
            )}

          </AnimatePresence>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
