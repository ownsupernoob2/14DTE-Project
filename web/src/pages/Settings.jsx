import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { AnimatePresence, motion } from 'framer-motion'
import Navbar from '../components/Navbar'
import FaceCaptureModal from '../components/FaceCaptureModal'
import BarcodeCaptureModal from '../components/BarcodeCaptureModal'
import { useServerStatus } from '../contexts/ServerStatusContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'
const AUTHORIZED_ADMIN_EMAIL = 'marminamina3@gmail.com'

export default function Settings() {
  const { user, logout, getAccessTokenSilently } = useAuth0()
  const [showFaceModal, setShowFaceModal] = useState(false)
  const [showBarcodeModal, setShowBarcodeModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const { isServerUp } = useServerStatus()
  const [isDeleting, setIsDeleting] = useState(false)

  // Linked student ID: null while loading, '' when none is linked.
  const [studentID, setStudentID] = useState(null)
  const [isUnlinking, setIsUnlinking] = useState(false)

  // Timetable check
  const [hasTimetable, setHasTimetable] = useState(() => Boolean(localStorage.getItem('timetable_ics_url')))

  // Theme & Language
  const [theme, setTheme] = useState(() => localStorage.getItem('mirror_theme') || 'oled-black')
  const [language, setLanguage] = useState(() => localStorage.getItem('mirror_lang') || 'en-NZ')

  const changeTheme = (newTheme) => {
    setTheme(newTheme)
    localStorage.setItem('mirror_theme', newTheme)
    document.documentElement.setAttribute('data-theme', newTheme)
  }

  const changeLanguage = (newLang) => {
    setLanguage(newLang)
    localStorage.setItem('mirror_lang', newLang)
  }

  const lastScan = localStorage.getItem('lastFaceScan')
  const scanTime = lastScan ? parseInt(lastScan, 10) : 0
  const isScanRecent = (Date.now() - scanTime) < 24 * 60 * 60 * 1000

  const hoursUntilUpdate = isScanRecent
    ? Math.ceil((24 * 60 * 60 * 1000 - (Date.now() - scanTime)) / (60 * 60 * 1000))
    : 0

  const userEmail = (user?.email || '').toLowerCase().trim()
  const isAdmin = userEmail === AUTHORIZED_ADMIN_EMAIL
  const hasBarcode = Boolean(studentID && studentID.trim())
  const hasFace = Boolean(lastScan)

  // Calculate onboarding progress (out of 3)
  const stepsCompleted = (hasBarcode ? 1 : 0) + (hasFace ? 1 : 0) + (hasTimetable ? 1 : 0)
  const progressPercent = Math.round((stepsCompleted / 3) * 100)

  useEffect(() => {
    let cancelled = false

    const loadStudentID = async () => {
      try {
        const token = await getAccessTokenSilently()
        const res = await fetch(`${API_URL}/api/users/me/barcode`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) throw new Error(`status ${res.status}`)
        const body = await res.json()
        if (!cancelled) setStudentID(body.barcode || '')
      } catch {
        if (!cancelled) setStudentID('')
      }
    }

    const checkTimetable = async () => {
      if (localStorage.getItem('timetable_ics_url')) {
        setHasTimetable(true)
        return
      }
      try {
        const token = await getAccessTokenSilently()
        const res = await fetch(`${API_URL}/api/timetable/ics`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (res.ok) {
          const data = await res.json()
          if (!cancelled && data.ics_url) {
            setHasTimetable(true)
            localStorage.setItem('timetable_ics_url', data.ics_url)
          }
        }
      } catch { /* silent */ }
    }

    if (isServerUp) {
      loadStudentID()
      checkTimetable()
    }
    return () => { cancelled = true }
  }, [isServerUp, getAccessTokenSilently])

  const unlinkStudentID = async () => {
    setIsUnlinking(true)
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/users/me/barcode`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        setStudentID('')
      } else {
        alert('Failed to unlink student ID. Please try again.')
      }
    } catch {
      alert('Error connecting to server')
    } finally {
      setIsUnlinking(false)
    }
  }

  const confirmDeleteFace = async () => {
    setIsDeleting(true)
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/faces/me`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        localStorage.removeItem('lastFaceScan')
        setShowDeleteConfirm(false)
        window.location.reload()
      } else {
        alert('Failed to delete face data. Please try again.')
      }
    } catch {
      alert('Error connecting to server')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#000000] text-white flex flex-col font-sans selection:bg-[#4fc3ff] selection:text-black">
      <Navbar />

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-8">
        {/* Header */}
        <header className="border-b border-[#1c1c1c] pb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold uppercase tracking-wider bg-[#4fc3ff]/10 text-[#4fc3ff] border border-[#4fc3ff]/20">
              King's High Smart Mirror · Preferences
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Account &amp; Identity Management
          </h1>
          <p className="text-xs sm:text-sm text-[#8f8f8f] mt-1.5 leading-relaxed">
            Link your physical student ID barcode, enroll your biometric face scan, and personalize your mirror dashboard.
          </p>
        </header>

        {/* User Profile Pill */}
        {user && (
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-2xl p-4 sm:p-5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <img
                src={user.picture}
                alt={user.name}
                className="w-12 h-12 rounded-xl object-cover border border-[#262626]"
              />
              <div>
                <h3 className="text-base font-bold text-white tracking-tight">{user.name}</h3>
                <p className="text-xs text-[#8f8f8f] font-mono">{user.email}</p>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-500/30">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Authenticated
            </span>
          </div>
        )}

        {/* Onboarding Checklist Card */}
        <section className="bg-gradient-to-r from-[#0d1624] via-[#0b101b] to-[#0a0a0a] border border-[#1e2f47] rounded-2xl p-5 sm:p-6 flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#1e2f47]/60 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#4fc3ff] text-lg">checklist</span>
                <h2 className="text-sm font-bold text-white tracking-wide uppercase font-mono">
                  Mirror Onboarding Checklist
                </h2>
              </div>
              <p className="text-xs text-[#9bb0c9] mt-0.5">
                Complete these 3 setup steps for seamless touchless authentication at the mirror.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-[#8f8f8f]">Progress:</span>
              <span className="text-xs font-mono font-bold text-[#4fc3ff]">
                {stepsCompleted} / 3 Completed ({progressPercent}%)
              </span>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-[#05080f] rounded-full h-2 overflow-hidden border border-[#1e2f47]">
            <motion.div
              className="bg-[#4fc3ff] h-full rounded-full shadow-sm shadow-[#4fc3ff]/50"
              initial={{ width: 0 }}
              animate={{ width: `${progressPercent}%` }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
            />
          </div>

          {/* Checklist Items */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            {/* Step 1 */}
            <div className={`p-3.5 rounded-xl border flex flex-col gap-1.5 transition-colors ${
              hasBarcode
                ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                : 'bg-[#000000]/40 border-[#262626] text-[#cbd5e1]'
            }`}>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider font-bold">Step 1 · Required</span>
                <span className="material-symbols-outlined text-base">
                  {hasBarcode ? 'check_circle' : 'radio_button_unchecked'}
                </span>
              </div>
              <span className="text-xs font-bold text-white">Student ID Barcode</span>
              <span className="text-[11px] text-[#8f8f8f] leading-snug">
                {hasBarcode ? `Linked (${studentID})` : 'Required identity anchor for mirror.'}
              </span>
            </div>

            {/* Step 2 */}
            <div className={`p-3.5 rounded-xl border flex flex-col gap-1.5 transition-colors ${
              hasFace
                ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                : hasBarcode
                ? 'bg-[#4fc3ff]/10 border-[#4fc3ff]/30 text-[#4fc3ff]'
                : 'bg-[#000000]/20 border-white/5 text-[#555555]'
            }`}>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider font-bold">Step 2 · Biometrics</span>
                <span className="material-symbols-outlined text-base">
                  {hasFace ? 'check_circle' : hasBarcode ? 'face' : 'lock'}
                </span>
              </div>
              <span className="text-xs font-bold text-white">Face Scan Enrolment</span>
              <span className="text-[11px] text-[#8f8f8f] leading-snug">
                {hasFace ? 'Enrolled & Active' : hasBarcode ? 'Ready to register' : 'Locked until Barcode is linked'}
              </span>
            </div>

            {/* Step 3 */}
            <div className={`p-3.5 rounded-xl border flex flex-col gap-1.5 transition-colors ${
              hasTimetable
                ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                : 'bg-[#000000]/40 border-[#262626] text-[#cbd5e1]'
            }`}>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider font-bold">Step 3 · Schedule</span>
                <span className="material-symbols-outlined text-base">
                  {hasTimetable ? 'check_circle' : 'radio_button_unchecked'}
                </span>
              </div>
              <span className="text-xs font-bold text-white">KAMAR Timetable</span>
              <span className="text-[11px] text-[#8f8f8f] leading-snug">
                {hasTimetable ? 'Synced from ICS feed' : 'Link feed in Timetable tab'}
              </span>
            </div>
          </div>
        </section>

        {/* Section: Student ID Barcode Authentication */}
        <section className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-2xl p-6 flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#1c1c1c] pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#4fc3ff]">badge</span>
                <h2 className="text-lg font-bold text-white tracking-tight">
                  Student ID Barcode Link
                </h2>
              </div>
              <p className="text-xs text-[#8f8f8f] mt-1">
                Your student ID number acts as your physical sign-in key and verified identity anchor.
              </p>
            </div>

            {hasBarcode && (
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-500/30 shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Linked
              </span>
            )}
          </div>

          {hasBarcode ? (
            <div className="bg-[#05080f] border border-[#1e2f47] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <span className="text-[10px] font-mono text-[#71859e] uppercase tracking-wider block">
                  Active Student ID Number
                </span>
                <span className="text-lg font-mono font-bold text-white tracking-widest mt-0.5 block">
                  {studentID}
                </span>
                <p className="text-xs text-[#8f8f8f] mt-1">
                  Hold card steady in the slot below the smart mirror to instantly sign in without touch.
                </p>
              </div>

              <div className="flex items-center gap-2.5 shrink-0">
                <button
                  onClick={() => setShowBarcodeModal(true)}
                  disabled={!isServerUp}
                  className="px-4 py-2 rounded-xl text-xs font-mono font-bold uppercase bg-[#141414] hover:bg-[#1f1f1f] border border-[#2e2e2e] text-[#d0d0d0] hover:text-white transition-colors cursor-pointer"
                >
                  Change ID
                </button>
                <button
                  onClick={unlinkStudentID}
                  disabled={isUnlinking || !isServerUp}
                  className="px-4 py-2 rounded-xl text-xs font-mono font-bold uppercase bg-red-950/30 hover:bg-red-950/50 border border-red-800/40 text-red-400 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {isUnlinking ? 'Unlinking...' : 'Unlink'}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#140e0a] border border-[#4a2612] rounded-xl p-4">
              <div>
                <h4 className="text-sm font-bold text-[#ffb020] flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-base">warning</span>
                  No Student ID Linked Yet
                </h4>
                <p className="text-xs text-[#c9a68a] mt-1 max-w-lg leading-relaxed">
                  Scanning your student ID card or entering your student ID number links your account and unlocks biometric face registration.
                </p>
              </div>

              <button
                onClick={() => setShowBarcodeModal(true)}
                disabled={!isServerUp || studentID === null}
                className="px-5 py-2.5 rounded-xl text-xs font-mono font-bold uppercase bg-[#4fc3ff] hover:bg-[#38b2ee] text-black transition-all cursor-pointer disabled:opacity-50 shadow-lg shadow-[#4fc3ff]/10 shrink-0"
              >
                {studentID === null ? 'Checking...' : 'Link Student ID Barcode'}
              </button>
            </div>
          )}
        </section>

        {/* Section: Biometric Face Recognition */}
        <section className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-2xl p-6 flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#1c1c1c] pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#4fc3ff]">face</span>
                <h2 className="text-lg font-bold text-white tracking-tight">
                  Biometric Face Recognition
                </h2>
              </div>
              <p className="text-xs text-[#8f8f8f] mt-1">
                Walk up to the mirror and get instantly recognized without touching the glass or scanning a card.
              </p>
            </div>

            {hasFace && (
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-500/30 shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Active Scan
              </span>
            )}
          </div>

          {/* Gating Logic: Require Barcode First */}
          {!hasBarcode ? (
            <div className="bg-[#121212] border border-[#262626] rounded-xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#222222] border border-[#333333] flex items-center justify-center text-[#888888] shrink-0 mt-0.5">
                  <span className="material-symbols-outlined text-xl">lock</span>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white">Face Scan Locked</h4>
                  <p className="text-xs text-[#8f8f8f] mt-1 max-w-lg leading-relaxed">
                    Student ID barcode must be linked first. This prevents misidentification and ensures a fallback sign-in is always available if lighting or backlight is unideal.
                  </p>
                </div>
              </div>

              <button
                onClick={() => setShowBarcodeModal(true)}
                className="px-4 py-2.5 rounded-xl text-xs font-mono font-bold uppercase bg-[#1e2f47] hover:bg-[#283e5c] text-[#4fc3ff] border border-[#4fc3ff]/30 transition-all cursor-pointer shrink-0"
              >
                Link Barcode to Unlock
              </button>
            </div>
          ) : isScanRecent ? (
            <div className="bg-[#05080f] border border-[#1e2f47] rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <strong className="text-sm font-bold text-white block">Face Scan Registered</strong>
                <p className="text-xs text-[#9bb0c9] mt-1 leading-relaxed">
                  Your biometric model is active. Can be updated in {hoursUntilUpdate} hour{hoursUntilUpdate !== 1 ? 's' : ''}. Delete below to re-scan sooner.
                </p>
              </div>

              <button
                onClick={() => setShowDeleteConfirm(true)}
                disabled={isDeleting || !isServerUp}
                className="px-4 py-2 rounded-xl text-xs font-mono font-bold uppercase bg-red-950/30 hover:bg-red-950/50 border border-red-800/40 text-red-400 transition-colors cursor-pointer shrink-0"
              >
                Delete &amp; Re-scan
              </button>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#05080f] border border-[#1e2f47] rounded-xl p-4">
              <div>
                <h4 className="text-sm font-bold text-white flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-emerald-400 text-base">verified</span>
                  Student ID Verified · Ready for Face Scan
                </h4>
                <p className="text-xs text-[#9bb0c9] mt-1 max-w-lg leading-relaxed">
                  Capture 10 rapid webcam frames to train your biometric model on the server.
                </p>
              </div>

              <button
                onClick={() => setShowFaceModal(true)}
                disabled={!isServerUp}
                className="px-5 py-2.5 rounded-xl text-xs font-mono font-bold uppercase bg-[#4fc3ff] hover:bg-[#38b2ee] text-black transition-all cursor-pointer disabled:opacity-50 shadow-lg shadow-[#4fc3ff]/10 shrink-0"
              >
                {isServerUp ? '📸 Register Face Scan' : 'Server Offline'}
              </button>
            </div>
          )}
        </section>

        {/* Section: Administration (Admin only) */}
        {isAdmin && (
          <section className="bg-gradient-to-r from-[#0d1624] via-[#0b101b] to-[#0a0a0a] border border-[#1e2f47] rounded-2xl p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-[#1e2f47]/60 pb-3">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#4fc3ff]">science</span>
                <h2 className="text-lg font-bold text-white tracking-tight">
                  Administration &amp; Telemetry
                </h2>
              </div>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase bg-[#4fc3ff]/15 text-[#4fc3ff] border border-[#4fc3ff]/30">
                Superuser Access
              </span>
            </div>

            <p className="text-xs text-[#9bb0c9] leading-relaxed">
              Access the live A/B testing observatory, gesture analytics, session duration metrics, and download raw telemetry datasets.
            </p>

            <div className="pt-2">
              <Link
                to="/admin"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-mono font-bold uppercase bg-[#4fc3ff] hover:bg-[#38b2ee] text-black transition-all cursor-pointer shadow-lg shadow-[#4fc3ff]/10"
              >
                <span className="material-symbols-outlined text-base">analytics</span>
                Open Admin Analytics Dashboard →
              </Link>
            </div>
          </section>
        )}

        {/* Section: Display Theme & Regional Language Preferences */}
        <section className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-2xl p-6 flex flex-col gap-5">
          <div className="border-b border-[#1c1c1c] pb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[#4fc3ff]">palette</span>
              <h2 className="text-lg font-bold text-white tracking-tight">
                {language === 'mi-NZ' ? 'Āhua me te Reo' : 'Appearance & Regional Language'}
              </h2>
            </div>
            <span className="text-[11px] font-mono text-[#8f8f8f]">
              {language === 'mi-NZ' ? 'Pūnaha Tautuhinga' : 'Active System Config'}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Theme Selector */}
            <div className="flex flex-col gap-2.5">
              <label className="text-xs font-mono text-[#8f8f8f] uppercase tracking-wider font-bold">
                {language === 'mi-NZ' ? 'Kaupapa Ataata' : 'Portal Theme (Smart Mirror Contrast)'}
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: 'oled-black', name: 'OLED Pure Black', preview: 'bg-black border-[#222]' },
                  { id: 'cyber-cyan', name: 'Cyber Neon Cyan', preview: 'bg-[#040d17] border-[#4fc3ff]/50' },
                  { id: 'midnight-navy', name: 'Deep Midnight', preview: 'bg-[#080d1a] border-[#38bdf8]/30' },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => changeTheme(t.id)}
                    className={`p-3 rounded-xl border flex flex-col gap-2 text-left transition-all cursor-pointer ${
                      theme === t.id
                        ? 'border-[#4fc3ff] bg-[#4fc3ff]/10 shadow-lg shadow-[#4fc3ff]/15'
                        : 'border-[#1c1c1c] bg-[#050505] hover:border-[#333]'
                    }`}
                  >
                    <div className={`w-full h-5 rounded ${t.preview} border`} />
                    <span className="text-[11px] font-mono font-bold text-white leading-tight">
                      {t.name}
                    </span>
                    <span className="text-[9px] font-mono text-[#8f8f8f]">
                      {theme === t.id ? '✓ Active' : 'Select'}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Language Selector */}
            <div className="flex flex-col gap-2.5">
              <label className="text-xs font-mono text-[#8f8f8f] uppercase tracking-wider font-bold">
                {language === 'mi-NZ' ? 'Reo Pūnaha' : 'Regional Language / Reo'}
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => changeLanguage('en-NZ')}
                  className={`p-3.5 rounded-xl border flex flex-col gap-1 transition-all text-left cursor-pointer ${
                    language === 'en-NZ'
                      ? 'border-[#4fc3ff] bg-[#4fc3ff]/10 text-white'
                      : 'border-[#1c1c1c] bg-[#050505] text-[#8f8f8f] hover:border-[#333]'
                  }`}
                >
                  <span className="text-xs font-bold text-white font-mono">English (New Zealand)</span>
                  <span className="text-[11px] text-[#8f8f8f]">Default school portal dialect</span>
                  <span className="text-[10px] font-mono text-[#4fc3ff] mt-1">
                    {language === 'en-NZ' ? '✓ Selected' : 'Choose'}
                  </span>
                </button>

                <button
                  onClick={() => changeLanguage('mi-NZ')}
                  className={`p-3.5 rounded-xl border flex flex-col gap-1 transition-all text-left cursor-pointer ${
                    language === 'mi-NZ'
                      ? 'border-[#4fc3ff] bg-[#4fc3ff]/10 text-white'
                      : 'border-[#1c1c1c] bg-[#050505] text-[#8f8f8f] hover:border-[#333]'
                  }`}
                >
                  <span className="text-xs font-bold text-white font-mono">Te Reo Māori</span>
                  <span className="text-[11px] text-[#8f8f8f]">He reo whai mana o Aotearoa</span>
                  <span className="text-[10px] font-mono text-[#4fc3ff] mt-1">
                    {language === 'mi-NZ' ? '✓ Kōwhiria' : 'Kōwhiri'}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Section: Policies & Privacy */}
        <section className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-2xl p-6 flex flex-col gap-4">
          <div className="border-b border-[#1c1c1c] pb-3">
            <h2 className="text-sm font-mono uppercase font-bold text-[#888888] tracking-widest">
              Biometric Privacy &amp; Legal Policies
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Link
              to="/privacy"
              className="bg-[#05080f] hover:bg-[#0d1624] border border-[#1e2f47]/50 hover:border-[#4fc3ff]/40 p-4 rounded-xl flex items-center justify-between transition-colors group"
            >
              <div>
                <h4 className="text-sm font-bold text-white group-hover:text-[#4fc3ff] transition-colors">
                  Biometric Privacy Policy
                </h4>
                <p className="text-[11px] text-[#71859e] mt-0.5">
                  Student biometric vector storage &amp; automatic deletion.
                </p>
              </div>
              <span className="material-symbols-outlined text-[#71859e] group-hover:text-[#4fc3ff] transition-colors">
                arrow_forward
              </span>
            </Link>

            <Link
              to="/terms"
              className="bg-[#05080f] hover:bg-[#0d1624] border border-[#1e2f47]/50 hover:border-[#4fc3ff]/40 p-4 rounded-xl flex items-center justify-between transition-colors group"
            >
              <div>
                <h4 className="text-sm font-bold text-white group-hover:text-[#4fc3ff] transition-colors">
                  Terms &amp; Acceptable Use
                </h4>
                <p className="text-[11px] text-[#71859e] mt-0.5">
                  High school smart mirror fair usage guidelines.
                </p>
              </div>
              <span className="material-symbols-outlined text-[#71859e] group-hover:text-[#4fc3ff] transition-colors">
                arrow_forward
              </span>
            </Link>
          </div>
        </section>

        {/* Section: Danger Zone & Logout */}
        <section className="bg-[#0a0a0a] border border-red-950/30 rounded-2xl p-6 flex flex-col gap-4">
          <div className="border-b border-red-950/40 pb-3 flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase font-bold text-red-400 tracking-widest flex items-center gap-1.5">
              <span className="material-symbols-outlined text-base">dangerous</span>
              Session &amp; Data Control
            </h2>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isDeleting || !isServerUp || !hasFace}
              className="w-full sm:w-auto px-4 py-2.5 rounded-xl text-xs font-mono font-bold uppercase bg-red-950/20 hover:bg-red-950/40 border border-red-800/40 text-red-400 transition-colors cursor-pointer disabled:opacity-40"
            >
              Delete Face Recognition Data
            </button>

            <button
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
              className="w-full sm:w-auto px-5 py-2.5 rounded-xl text-xs font-mono font-bold uppercase bg-[#141414] hover:bg-[#1f1f1f] border border-[#2e2e2e] text-[#d0d0d0] hover:text-white transition-colors cursor-pointer"
            >
              Log Out of Portal
            </button>
          </div>
        </section>
      </main>

      {/* Modals */}
      <FaceCaptureModal isOpen={showFaceModal} onClose={() => setShowFaceModal(false)} />

      <BarcodeCaptureModal
        isOpen={showBarcodeModal}
        onClose={() => setShowBarcodeModal(false)}
        onBarcodeSaved={(code) => setStudentID(code)}
      />

      {/* Delete Confirmation Modal */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => e.target === e.currentTarget && !isDeleting && setShowDeleteConfirm(false)}
          >
            <motion.div
              className="bg-[#0a0a0a] border border-red-900/50 rounded-2xl p-6 max-w-md w-full flex flex-col gap-4 text-center shadow-2xl"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-12 h-12 rounded-full bg-red-950/50 border border-red-800/50 flex items-center justify-center text-red-400 mx-auto">
                <span className="material-symbols-outlined text-2xl">warning</span>
              </div>

              <div>
                <span className="text-[10px] font-mono uppercase text-red-400 font-bold tracking-widest block">
                  Destructive Action
                </span>
                <h3 className="text-xl font-bold text-white mt-1">Delete Face Recognition Data?</h3>
                <p className="text-xs text-[#8f8f8f] mt-2 leading-relaxed">
                  This permanently erases your 128-dimensional face vectors from the mirror database. You will need to scan your student ID barcode to sign in until a new face scan is registered.
                </p>
              </div>

              <div className="flex items-center gap-3 mt-2">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={isDeleting}
                  className="flex-1 py-2.5 rounded-xl text-xs font-mono uppercase font-bold border border-[#2e2e2e] text-[#a0a0a0] hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDeleteFace}
                  disabled={isDeleting || !isServerUp}
                  className="flex-1 py-2.5 rounded-xl text-xs font-mono uppercase font-bold bg-red-600 hover:bg-red-500 text-white transition-colors cursor-pointer disabled:opacity-50"
                >
                  {isDeleting ? 'Deleting...' : 'Delete Permanently'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
