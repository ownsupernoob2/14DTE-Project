import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import BarcodeScannerComponent from 'react-qr-barcode-scanner'
import step1Img from '../assets/barcode/1.png'
import step2Img from '../assets/barcode/2.png'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// ── Validation (mirrors server/handlers_barcode.go) ─────────────────────────
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

// ── Audio feedback ───────────────────────────────────────────────────────────
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
  } catch { /* audio is a nicety; a blocked AudioContext must not break the scan */ }
}

// ── Slides definition ─────────────────────────────────────────────────────────
const SLIDES = [
  {
    step: 1,
    title: 'FIND THE BARCODE ON YOUR STUDENT ID CARD',
    desc: 'Locate the barcode printed on your student ID card. It is usually on the back or bottom of the front face.',
    img: step1Img,
  },
  {
    step: 2,
    title: 'HOLD BARCODE IN FRONT OF THE CAMERA',
    desc: 'Use the "Scan Barcode" tab below. Hold your card flat so the barcode sits inside the dashed targeting frame.',
    img: step2Img,
  },
  {
    step: 3,
    title: 'NO CARD? TYPE YOUR ID NUMBER INSTEAD',
    desc: 'Switch to the "Type ID" tab below and enter your student number. You can find it printed on the card or in KAMAR.',
    isArrow: true,
  },
]

// ── Main modal ────────────────────────────────────────────────────────────────
export default function BarcodeCaptureModal({ isOpen, onClose, onBarcodeSaved }) {
  const { getAccessTokenSilently } = useAuth0()

  const [slide, setSlide]           = useState(0)
  const [phase, setPhase]           = useState('input')
  const [mode, setMode]             = useState('scan')
  const [errorMsg, setErrorMsg]     = useState('')
  const [savedCode, setSavedCode]   = useState('')
  const [manualCode, setManualCode] = useState('')
  const [stopStream, setStopStream] = useState(false)

  const handledRef = useRef(false)

  useEffect(() => {
    if (isOpen) {
      setSlide(0)
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

  const switchMode = (next) => {
    setMode(next)
    setStopStream(next !== 'scan')
    if (next === 'scan') handledRef.current = false
    setErrorMsg('')
  }

  const linkStudentID = async (rawCode) => {
    const code = normalizeStudentID(rawCode)
    const invalid = validateStudentID(code)
    if (invalid) { setErrorMsg(invalid); setPhase('error'); return }

    setPhase('saving')
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/users/me/barcode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
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

  const handleClose = () => { setStopStream(true); onClose() }

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
  const currentSlide = SLIDES[slide]

  const tabCls = (active) =>
    'flex-1 py-2.5 px-3 text-xs font-bold font-mono uppercase tracking-widest border transition-all cursor-pointer rounded-none ' +
    (active
      ? 'bg-white text-black border-white'
      : 'bg-black text-[#888888] border-[#222222] hover:border-[#555555] hover:text-white')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm">
      <AnimatePresence mode="wait">

        {/* INPUT phase */}
        {phase === 'input' && (
          <motion.div
            key="input"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.2 }}
            className="bg-[#0a0a0a] border border-[#222222] rounded-none w-full max-w-xl p-6 flex flex-col gap-5 text-white font-mono shadow-2xl select-none"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-white">
                LINK STUDENT ID CARD
              </span>
              <button
                onClick={handleClose}
                className="text-[#888888] hover:text-white text-xs font-mono uppercase cursor-pointer transition-colors"
              >
                X
              </button>
            </div>

            {/* Slideshow */}
            <div className="bg-[#0e0e0e] p-5 flex flex-col gap-3 border border-[#1a1a1a]">

              {/* Step counter + dot nav */}
              <div className="flex items-center justify-between text-[11px] text-[#888888]">
                <span className="uppercase font-bold tracking-widest text-white">
                  STEP {currentSlide.step} / {SLIDES.length}
                </span>
                <div className="flex gap-1.5">
                  {SLIDES.map((_, idx) => (
                    <button
                      key={idx}
                      onClick={() => setSlide(idx)}
                      className={`w-6 h-1 transition-colors cursor-pointer ${
                        idx === slide ? 'bg-white' : 'bg-[#2a2a2a] hover:bg-[#444444]'
                      }`}
                    />
                  ))}
                </div>
              </div>

              {/* Title + description */}
              <div className="flex flex-col gap-1">
                <h3 className="text-xs font-bold text-white uppercase tracking-tight">
                  {currentSlide.title}
                </h3>
                <p className="text-xs text-[#aaaaaa] leading-relaxed">
                  {currentSlide.desc}
                </p>
              </div>

              {/* Visual area */}
              <AnimatePresence mode="wait">
                <motion.div
                  key={slide}
                  initial={{ opacity: 0, x: 14 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -14 }}
                  transition={{ duration: 0.18 }}
                >
                  <div className="py-2 flex flex-col items-center justify-center min-h-[140px] bg-[#000000] border border-[#1c1c1c] p-2">
                    {currentSlide.img && (
                      <img
                        src={currentSlide.img}
                        alt={currentSlide.title}
                        className="w-full max-h-52 object-contain"
                      />
                    )}
                    {currentSlide.isArrow && (
                      <div className="flex flex-col items-center gap-2 py-4">
                        <span className="text-xs text-[#aaaaaa]">USE THE TYPE ID TAB BELOW:</span>
                        <span className="text-3xl text-white animate-bounce">v</span>
                      </div>
                    )}
                  </div>
                </motion.div>
              </AnimatePresence>

              {/* Prev / Next */}
              <div className="flex items-center justify-between pt-1">
                <button
                  type="button"
                  onClick={() => setSlide(s => Math.max(0, s - 1))}
                  disabled={slide === 0}
                  className="px-6 py-3 border border-[#333333] disabled:opacity-20 text-xs font-mono font-bold uppercase hover:border-[#666666] text-[#aaaaaa] hover:text-white transition-colors cursor-pointer rounded-none"
                >
                  &larr; PREV
                </button>
                <button
                  type="button"
                  onClick={() => setSlide(s => Math.min(SLIDES.length - 1, s + 1))}
                  disabled={slide === SLIDES.length - 1}
                  className="px-10 py-3.5 bg-white disabled:opacity-20 text-black hover:bg-[#e0e0e0] text-sm font-mono font-bold uppercase tracking-wider transition-all cursor-pointer rounded-none shadow-md"
                >
                  NEXT &rarr;
                </button>
              </div>
            </div>

            {/* Scan / Type area -- always visible below the slides */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <label className="text-[10px] text-[#888888] uppercase tracking-wider font-bold">
                  SCAN OR ENTER YOUR STUDENT ID
                </label>
              </div>

              {/* Mode tabs */}
              <div className="flex gap-2 w-full">
                <button className={tabCls(mode === 'scan')}   onClick={() => switchMode('scan')}>
                  SCAN BARCODE
                </button>
                <button className={tabCls(mode === 'manual')} onClick={() => switchMode('manual')}>
                  TYPE ID
                </button>
              </div>

              <AnimatePresence mode="wait">
                {mode === 'scan' ? (
                  <motion.div
                    key="scan"
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="flex flex-col items-center gap-2"
                  >
                    <div style={{
                      width: '100%', maxWidth: 340, height: 200,
                      overflow: 'hidden', position: 'relative',
                      background: '#000', border: '1px solid #1c1c1c',
                    }}>
                      <BarcodeScannerComponent
                        width={340}
                        height={200}
                        onUpdate={handleScan}
                        stopStream={stopStream}
                      />
                      {/* Targeting frame overlay */}
                      <div style={{
                        position: 'absolute', top: '50%', left: '50%',
                        transform: 'translate(-50%, -50%)',
                        width: '72%', height: '52%',
                        border: '1.5px dashed rgba(255,255,255,0.4)',
                        boxShadow: '0 0 0 9999px rgba(0,0,0,0.35)',
                        pointerEvents: 'none',
                      }} />
                    </div>
                    <p className="text-[11px] text-[#555555] font-mono text-center">
                      Hold barcode flat inside the frame. Camera not working? Use TYPE ID.
                    </p>
                  </motion.div>
                ) : (
                  <motion.div
                    key="manual"
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                  >
                    <form
                      className="flex flex-col gap-2"
                      onSubmit={(e) => { e.preventDefault(); if (canSubmitManual) linkStudentID(manualCode) }}
                    >
                      <label htmlFor="student-id-input" className="text-[10px] text-[#666666] uppercase tracking-wider font-bold">
                        STUDENT ID NUMBER
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
                        className="w-full bg-[#0e0e0e] border border-[#262626] focus:border-white text-white px-3.5 py-3 text-sm font-mono rounded-none outline-none transition-colors tracking-widest"
                        style={{ borderColor: manualError ? 'rgba(239,68,68,0.5)' : undefined }}
                      />
                      <div className="min-h-[16px] text-xs font-mono">
                        {manualError
                          ? <span className="text-red-400">{manualError}</span>
                          : manualNormalized
                            ? <span className="text-[#555555]">Will save as <strong className="text-white">{manualNormalized}</strong></span>
                            : null}
                      </div>
                      <button
                        type="submit"
                        disabled={!canSubmitManual}
                        className="w-full py-3 bg-white text-black text-xs font-bold font-mono uppercase tracking-wider rounded-none hover:bg-[#e0e0e0] disabled:opacity-40 transition-colors cursor-pointer"
                      >
                        LINK THIS ID
                      </button>
                    </form>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={handleClose}
                  className="px-4 py-2 border border-[#222222] text-[#888888] hover:text-white text-xs uppercase font-bold rounded-none cursor-pointer transition-colors"
                >
                  CLOSE
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* SAVING */}
        {phase === 'saving' && (
          <motion.div
            key="saving"
            initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="bg-[#0a0a0a] border border-[#222222] rounded-none w-full max-w-sm p-10 flex flex-col items-center gap-5 text-white font-mono shadow-2xl"
          >
            <div className="fc-pulse-ring" />
            <h2 className="text-sm font-bold uppercase tracking-widest">LINKING STUDENT ID</h2>
            <p className="text-xs text-[#888888] text-center">Attaching this ID to your mirror layout...</p>
          </motion.div>
        )}

        {/* SUCCESS */}
        {phase === 'success' && (
          <motion.div
            key="success"
            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="bg-[#0a0a0a] border border-[#222222] rounded-none w-full max-w-sm p-10 flex flex-col items-center gap-5 text-white font-mono shadow-2xl"
          >
            <div style={{
              width: 64, height: 64, border: '1px solid #2a2a2a', borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0e0e0e',
            }}>
              <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                <path d="M7 16l7 7 11-11" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <h2 className="text-sm font-bold uppercase tracking-widest">STUDENT ID LINKED</h2>
            <p className="text-xs text-[#888888] text-center leading-relaxed">
              <strong style={{ fontFamily: 'ui-monospace, monospace', letterSpacing: '0.14em', color: '#fff' }}>{savedCode}</strong>
              <br />Scan this card at the mirror to sign in automatically.
            </p>
            <button
              onClick={handleClose}
              className="mt-2 px-8 py-3 bg-white text-black text-xs font-bold font-mono uppercase tracking-widest rounded-none hover:bg-[#e0e0e0] transition-colors cursor-pointer"
            >
              DONE
            </button>
          </motion.div>
        )}

        {/* ERROR */}
        {phase === 'error' && (
          <motion.div
            key="error"
            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="bg-[#0a0a0a] border border-[#222222] rounded-none w-full max-w-sm p-10 flex flex-col items-center gap-5 text-white font-mono shadow-2xl"
          >
            <div style={{
              width: 64, height: 64, border: '1px solid #2a2a2a', borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0e0e0e',
            }}>
              <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                <path d="M10 10l12 12M22 10L10 22" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            </div>
            <h2 className="text-sm font-bold uppercase tracking-widest">COULD NOT LINK ID</h2>
            <p className="text-xs text-[#888888] text-center">{errorMsg}</p>
            <div className="flex gap-3 mt-2">
              <button
                onClick={handleClose}
                className="px-5 py-2.5 border border-[#333333] text-[#888888] hover:text-white text-xs font-bold font-mono uppercase rounded-none cursor-pointer transition-colors"
              >
                CANCEL
              </button>
              <button
                onClick={retry}
                className="px-5 py-2.5 bg-white text-black hover:bg-[#e0e0e0] text-xs font-bold font-mono uppercase rounded-none cursor-pointer transition-colors"
              >
                TRY AGAIN
              </button>
            </div>
          </motion.div>
        )}

      </AnimatePresence>
    </div>
  )
}
