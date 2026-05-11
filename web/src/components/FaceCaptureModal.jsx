import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import Webcam from 'react-webcam'

const API_URL = 'https://api.smartmirror.me'
const TOTAL_PHOTOS = 10
const BURST_INTERVAL_MS = 500
const BRIGHTNESS_THRESHOLD = 40
const BRIGHTNESS_CHECK_MS = 200

const PRIVACY_TEXT = `Privacy Policy

Last updated: May 2026

1. Data Collection
Smart Mirror collects facial image data solely for the purpose of identifying registered users at the physical mirror terminal. Images are captured through your device camera during the registration process.

2. How Your Data Is Used
Your facial images are processed on our server to generate a mathematical encoding (a numerical representation of your facial geometry). This encoding is used exclusively to identify you at the Smart Mirror. Raw images are permanently deleted from our servers immediately after the encoding is generated.

3. Data Storage
Only the mathematical encoding derived from your face is stored. No raw photographs are retained. Encodings are stored securely and linked to your authenticated account.

4. Data Sharing
We do not sell, share, or disclose your facial data or encodings to any third party. Your data is used solely within this Smart Mirror system.

5. Data Deletion
You may request deletion of your facial encoding at any time through your account preferences. Upon deletion, you will no longer be recognised by the mirror system.

6. Security
All data is transmitted over encrypted connections. Server access is restricted and protected by authentication controls.

Terms of Use

1. Eligibility
Use of this face registration feature is limited to authorised users of the Smart Mirror system at Kings High School.

2. Consent
By registering your face, you consent to the collection, processing, and storage of your facial encoding as described in the Privacy Policy above.

3. Acceptable Use
You must only register your own face. Registering another person's face without their consent is strictly prohibited and may result in account suspension.

4. Accuracy
Face recognition is not infallible. The system may occasionally fail to identify you or may require re-registration if your appearance changes significantly.

5. Amendments
These terms may be updated from time to time. Continued use of the face registration feature constitutes acceptance of any revised terms.`

// Phases: 'intro' | 'consent' | 'capture' | 'uploading' | 'success' | 'error'

export default function FaceCaptureModal({ isOpen, onClose }) {
  const { getAccessTokenSilently } = useAuth0()

  const [phase, setPhase] = useState('intro')
  const [agreedPrivacy, setAgreedPrivacy] = useState(false)
  const [agreedTerms, setAgreedTerms] = useState(false)
  const [captureProgress, setCaptureProgress] = useState(0)
  const [brightness, setBrightness] = useState(255)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [framesUsed, setFramesUsed] = useState(0)
  const [isCameraReady, setIsCameraReady] = useState(false)
  const [cameraError, setCameraError] = useState(false)
  const [captureFlash, setCaptureFlash] = useState(false)

  const webcamRef = useRef(null)
  const canvasRef = useRef(null)
  const brightnessTimerRef = useRef(null)
  const burstTimerRef = useRef(null)
  const capturedImagesRef = useRef([])
  const phase1DoneRef = useRef(false)

  // ── Camera ──────────────────────────────────────────────────────────────────
  const handleUserMedia = useCallback(() => {
    setIsCameraReady(true)
    setCameraError(false)
  }, [])

  const handleUserMediaError = useCallback((err) => {
    console.error("Camera error:", err)
    setCameraError(true)
    setIsCameraReady(false)
  }, [])

  const stopCamera = useCallback(() => {
    clearInterval(brightnessTimerRef.current)
    clearInterval(burstTimerRef.current)
    setIsCameraReady(false)
  }, [])

  // ── Reset on open/close ──────────────────────────────────────────────────
  useEffect(() => {
    if (isOpen) {
      setPhase('intro')
      setAgreedPrivacy(false)
      setAgreedTerms(false)
      setCaptureProgress(0)
      capturedImagesRef.current = []
      phase1DoneRef.current = false
      setUploadProgress(0)
      setErrorMsg('')
      setFramesUsed(0)
      setIsCameraReady(false)
      setCameraError(false)
      setBrightness(255)
    } else {
      stopCamera()
    }
  }, [isOpen, stopCamera])

  useEffect(() => {
    if (phase !== 'capture') stopCamera()
  }, [phase, stopCamera])

  // ── Frame helpers ────────────────────────────────────────────────────────
  const snapFrame = useCallback(() => {
    if (!webcamRef.current) return null
    return webcamRef.current.getScreenshot()
  }, [])

  const measureBrightness = useCallback(() => {
    if (!webcamRef.current || !webcamRef.current.video) return 255
    const video = webcamRef.current.video
    if (!video.videoWidth) return 255
    const canvas = canvasRef.current
    if (!canvas) return 255

    canvas.width = 80
    canvas.height = 80
    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0, 80, 80)
    const data = ctx.getImageData(0, 0, 80, 80).data
    let sum = 0
    for (let i = 0; i < data.length; i += 4) {
      sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
    }
    return sum / (80 * 80)
  }, [])

  const addCapture = useCallback((dataUrl) => {
    if (!dataUrl) return
    setCaptureFlash(true)
    setTimeout(() => setCaptureFlash(false), 180)

    capturedImagesRef.current = [...capturedImagesRef.current, dataUrl]
    const count = capturedImagesRef.current.length
    setCaptureProgress(Math.round((count / TOTAL_PHOTOS) * 100))

    if (count === 1) phase1DoneRef.current = true

    if (count >= TOTAL_PHOTOS) {
      clearInterval(burstTimerRef.current)
      clearInterval(brightnessTimerRef.current)
      handleUpload(capturedImagesRef.current)
    }
  }, []) // eslint-disable-line

  // ── Brightness polling + user-initiated first capture ────────────────────────────
  useEffect(() => {
    if (phase !== 'capture' || !isCameraReady) return
    brightnessTimerRef.current = setInterval(() => {
      const lum = measureBrightness()
      setBrightness(lum)
    }, BRIGHTNESS_CHECK_MS)
    return () => clearInterval(brightnessTimerRef.current)
  }, [phase, isCameraReady, measureBrightness])

  const handleStartCapture = () => {
    if (!phase1DoneRef.current && brightness >= BRIGHTNESS_THRESHOLD && capturedImagesRef.current.length === 0) {
      addCapture(snapFrame())
    }
  }

  // ── Burst (photos 2-10) ──────────────────────────────────────────────────
  useEffect(() => {
    if (phase !== 'capture' || !isCameraReady) return
    burstTimerRef.current = setInterval(() => {
      if (!phase1DoneRef.current) return
      if (capturedImagesRef.current.length >= TOTAL_PHOTOS) return
      if (measureBrightness() < BRIGHTNESS_THRESHOLD) return
      addCapture(snapFrame())
    }, BURST_INTERVAL_MS)
    return () => clearInterval(burstTimerRef.current)
  }, [phase, isCameraReady, measureBrightness, snapFrame, addCapture])

  // ── Upload ───────────────────────────────────────────────────────────────
  const handleUpload = async (images) => {
    setPhase('uploading')
    setUploadProgress(10)
    stopCamera()
    try {
      const token = await getAccessTokenSilently()
      setUploadProgress(35)
      const res = await fetch(`${API_URL}/api/faces/train`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ images }),
      })
      setUploadProgress(90)
      if (res.ok) {
        const data = await res.json()
        setFramesUsed(data.frames_used || images.length)
        setUploadProgress(100)
        setPhase('success')
      } else {
        const data = await res.json().catch(() => ({}))
        setErrorMsg(data.error || 'Upload failed. Please try again.')
        setPhase('error')
      }
    } catch {
      setErrorMsg('The Smart Mirror server is offline, please try again later.')
      setPhase('error')
    }
  }

  const handleRetry = () => {
    capturedImagesRef.current = []
    phase1DoneRef.current = false
    setCaptureProgress(0)
    setUploadProgress(0)
    setErrorMsg('')
    setPhase('capture')
  }

  const handleClose = () => {
    stopCamera()
    onClose()
    setTimeout(() => {
      setPhase('intro')
      setAgreedPrivacy(false)
      setAgreedTerms(false)
      setCaptureProgress(0)
      capturedImagesRef.current = []
      phase1DoneRef.current = false
    }, 350)
  }

  if (!isOpen) return null

  const isTooDark = brightness < BRIGHTNESS_THRESHOLD
  const canProceed = agreedPrivacy && agreedTerms

  const slideVariants = {
    initial: { opacity: 0, x: 24 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: -24 },
  }

  return (
    <AnimatePresence>
      <motion.div
        key="backdrop"
        className="fc-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={(e) => e.target === e.currentTarget && handleClose()}
      >
        <motion.div
          className="fc-modal"
          initial={{ opacity: 0, scale: 0.94, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.94, y: 20 }}
          transition={{ type: 'spring', stiffness: 300, damping: 26 }}
        >
          <button className="fc-close" onClick={handleClose} aria-label="Close">&#x2715;</button>

          <AnimatePresence mode="wait">

            {/* INTRO */}
            {phase === 'intro' && (
              <motion.div key="intro" className="fc-phase" variants={slideVariants} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.25 }}>
                <p className="fc-overline">Face Registration</p>
                <h2 className="fc-title">Set Up Mirror Recognition</h2>
                <p className="fc-sub">
                  We will take 10 photos to train the mirror to recognise you. The process takes about 5 seconds. Raw images are deleted immediately after training — only a mathematical encoding is kept.
                </p>
                <ul className="fc-list">
                  <li>Sit in a well-lit area</li>
                  <li>Keep your face centred in the frame</li>
                  <li>Slowly rotate your head once prompted</li>
                  <li>Your images are never stored after training</li>
                </ul>
                <motion.button
                  className="fc-btn"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => setPhase('consent')}
                >
                  Continue
                </motion.button>
              </motion.div>
            )}

            {/* CONSENT */}
            {phase === 'consent' && (
              <motion.div key="consent" className="fc-phase" variants={slideVariants} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.25 }}>
                <p className="fc-overline">Privacy &amp; Terms</p>
                <h2 className="fc-title">Review &amp; Agree</h2>
                <p className="fc-sub">Please read and accept the following before registering your face.</p>
                <div className="fc-policy-scroll">
                  <pre className="fc-policy-text">{PRIVACY_TEXT}</pre>
                </div>
                <div className="fc-checks">
                  <label className="fc-check-row">
                    <input type="checkbox" checked={agreedPrivacy} onChange={(e) => setAgreedPrivacy(e.target.checked)} />
                    <span>I have read and agree to the <strong>Privacy Policy</strong></span>
                  </label>
                  <label className="fc-check-row">
                    <input type="checkbox" checked={agreedTerms} onChange={(e) => setAgreedTerms(e.target.checked)} />
                    <span>I have read and agree to the <strong>Terms of Use</strong></span>
                  </label>
                </div>
                <div className="fc-row-btns">
                  <motion.button className="fc-btn fc-btn-outline" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={() => setPhase('intro')}>
                    Back
                  </motion.button>
                  <motion.button
                    className="fc-btn"
                    style={{ opacity: canProceed ? 1 : 0.35, cursor: canProceed ? 'pointer' : 'not-allowed' }}
                    whileHover={canProceed ? { scale: 1.02 } : {}}
                    whileTap={canProceed ? { scale: 0.97 } : {}}
                    onClick={() => canProceed && setPhase('capture')}
                  >
                    Start Camera
                  </motion.button>
                </div>
              </motion.div>
            )}

            {/* CAPTURE */}
            {phase === 'capture' && (
              <motion.div key="capture" className="fc-phase fc-phase-capture" variants={slideVariants} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.25 }}>
                <p className="fc-overline">Step 3 of 3</p>
                <h2 className="fc-title" style={{ marginBottom: 0 }}>
                  {captureProgress === 0 ? 'Look straight at the camera' : 'Slowly rotate your head in a circle'}
                </h2>

                <AnimatePresence>
                  {isTooDark && (
                    <motion.div className="fc-dark-warn" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                      Too dark — move to a brighter area
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Circular camera */}
                <div className="fc-cam-ring">
                  <AnimatePresence>
                    {captureFlash && (
                      <motion.div key="flash" className="fc-flash" initial={{ opacity: 0.8 }} animate={{ opacity: 0 }} transition={{ duration: 0.18 }} />
                    )}
                  </AnimatePresence>
                  {cameraError ? (
                    <div className="fc-cam-msg">
                      <p>Camera access denied.</p>
                      <p style={{ opacity: 0.5, fontSize: '0.78rem' }}>Allow camera access in your browser settings.</p>
                    </div>
                  ) : (
                    <>
                      <Webcam
                        ref={webcamRef}
                        audio={false}
                        screenshotFormat="image/jpeg"
                        videoConstraints={{ width: 640, height: 640, facingMode: "user" }}
                        onUserMedia={handleUserMedia}
                        onUserMediaError={handleUserMediaError}
                        className="fc-video"
                        style={{ opacity: isCameraReady ? 1 : 0 }}
                      />
                      {!isCameraReady && (
                        <div className="fc-cam-msg">
                          <div className="fc-spinner" />
                          <p>Starting camera</p>
                        </div>
                      )}
                    </>
                  )}
                </div>

                <canvas ref={canvasRef} style={{ display: 'none' }} />

                {isCameraReady && capturedImagesRef.current.length === 0 && (
                  <motion.button
                    className="fc-btn"
                    style={{ marginTop: 16 }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={handleStartCapture}
                    disabled={isTooDark}
                  >
                    Start Capture (10 Photos)
                  </motion.button>
                )}

                {/* Progress bar only — no photo count */}
                <div className="fc-bar-track">
                  <motion.div
                    className="fc-bar-fill"
                    initial={{ width: '0%' }}
                    animate={{ width: `${captureProgress}%` }}
                    transition={{ duration: 0.4, ease: 'easeOut' }}
                  />
                </div>
              </motion.div>
            )}

            {/* UPLOADING */}
            {phase === 'uploading' && (
              <motion.div key="uploading" className="fc-phase fc-phase-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                <div className="fc-pulse-ring" />
                <h2 className="fc-title">Training Your Model</h2>
                <p className="fc-sub">Processing your photos. This takes just a moment.</p>
                <div className="fc-bar-track" style={{ maxWidth: 300 }}>
                  <motion.div className="fc-bar-fill" initial={{ width: '0%' }} animate={{ width: `${uploadProgress}%` }} transition={{ duration: 0.5, ease: 'easeOut' }} />
                </div>
              </motion.div>
            )}

            {/* SUCCESS */}
            {phase === 'success' && (
              <motion.div key="success" className="fc-phase fc-phase-center" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }}>
                <motion.div className="fc-status-ring fc-status-ok" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 350, damping: 18, delay: 0.1 }}>
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M7 16l7 7 11-11" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </motion.div>
                <h2 className="fc-title">Registration Complete</h2>
                <p className="fc-sub">
                  Trained on <strong>{framesUsed}</strong> photo{framesUsed !== 1 ? 's' : ''}. The mirror will now recognise you and load your personal layout. Raw images were deleted immediately after training.
                </p>
                <motion.button className="fc-btn" style={{ marginTop: 16 }} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleClose}>
                  Done
                </motion.button>
              </motion.div>
            )}

            {/* ERROR */}
            {phase === 'error' && (
              <motion.div key="error" className="fc-phase fc-phase-center" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }}>
                <div className="fc-status-ring fc-status-err">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M10 10l12 12M22 10L10 22" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                  </svg>
                </div>
                <h2 className="fc-title">Something Went Wrong</h2>
                <p className="fc-sub" style={{ color: 'rgba(255,255,255,0.5)' }}>{errorMsg}</p>
                <div className="fc-row-btns" style={{ marginTop: 24 }}>
                  <motion.button className="fc-btn fc-btn-outline" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleClose}>Cancel</motion.button>
                  <motion.button className="fc-btn" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleRetry}>Try Again</motion.button>
                </div>
              </motion.div>
            )}

          </AnimatePresence>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
