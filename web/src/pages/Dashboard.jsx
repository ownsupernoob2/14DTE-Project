import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import Navbar from '../components/Navbar'
import DailyNoticesWidget from '../components/DailyNoticesWidget'
import TimetableWidget from '../components/TimetableWidget'
import BarcodeCaptureModal from '../components/BarcodeCaptureModal'
import FaceCaptureModal from '../components/FaceCaptureModal'
import { useLanguage } from '../contexts/LanguageContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// ─── Onboarding Modal ────────────────────────────────────────────────────────
function OnboardingModal({ isOpen, onClose, onOpenBarcode, onOpenFace, onOpenTimetable }) {
  const [dontShowAgain, setDontShowAgain] = useState(false)
  const { t } = useLanguage()

  if (!isOpen) return null

  const handleClose = () => {
    if (dontShowAgain) {
      localStorage.setItem('hide_onboarding_modal', 'true')
    }
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        className="bg-[#0a0a0a] border border-[#222222] rounded-none w-full max-w-lg p-6 flex flex-col gap-5 text-white font-mono shadow-2xl select-none"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-3">
          <span className="text-xs font-bold uppercase tracking-wider text-white">
            {t('setup_guide')}
          </span>
          <button
            onClick={handleClose}
            className="text-[#888888] hover:text-white text-xs font-mono uppercase cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Description */}
        <p className="text-xs text-[#aaaaaa] leading-relaxed">
          {t('setup_desc')}
        </p>

        {/* Steps List */}
        <div className="flex flex-col gap-2.5">
          {/* Step 1: Barcode */}
          <div className="bg-[#121212] p-3.5 flex items-center justify-between border border-[#1a1a1a]">
            <div>
              <span className="text-xs font-bold text-white block">
                {t('barcode_step')}
              </span>
              <span className="text-[10px] text-[#888888]">Required identity anchor</span>
            </div>
            <button
              onClick={() => {
                handleClose()
                if (onOpenBarcode) onOpenBarcode()
              }}
              className="px-4 py-1.5 bg-white text-black text-xs font-bold uppercase rounded-none hover:bg-[#e0e0e0] cursor-pointer"
            >
              {t('link_btn')}
            </button>
          </div>

          {/* Step 2: Face AI (Optional) */}
          <div className="bg-[#121212] p-3.5 flex items-center justify-between border border-[#1a1a1a]">
            <div>
              <span className="text-xs font-bold text-white block">
                {t('face_step')}
              </span>
              <span className="text-[10px] text-[#888888]">Touchless recognition ({t('optional_tag')})</span>
            </div>
            <button
              onClick={() => {
                handleClose()
                if (onOpenFace) onOpenFace()
              }}
              className="px-4 py-1.5 bg-[#222222] text-white text-xs font-bold uppercase rounded-none hover:bg-[#333333] cursor-pointer"
            >
              {t('enroll_btn')}
            </button>
          </div>

          {/* Step 3: Timetable with ACTIVE button */}
          <div className="bg-[#121212] p-3.5 flex items-center justify-between border border-[#1a1a1a]">
            <div>
              <span className="text-xs font-bold text-white block">
                {t('timetable_step')}
              </span>
              <span className="text-[10px] text-[#888888]">KAMAR calendar feed link</span>
            </div>
            <button
              onClick={() => {
                handleClose()
                if (onOpenTimetable) onOpenTimetable()
              }}
              className="px-4 py-1.5 bg-white text-black text-xs font-bold uppercase rounded-none hover:bg-[#e0e0e0] cursor-pointer"
            >
              {t('connect_btn')}
            </button>
          </div>
        </div>

        {/* Footer with "Don't show this again" checkbox */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-3 border-t border-[#1c1c1c]">
          <label className="flex items-center gap-2 cursor-pointer text-xs text-[#888888] hover:text-white select-none">
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
              className="w-3.5 h-3.5 accent-white rounded-none cursor-pointer"
            />
            <span className="text-[11px] uppercase tracking-wider">{t('dont_show_again')}</span>
          </label>

          <button
            onClick={handleClose}
            className="w-full sm:w-auto px-5 py-2 bg-white text-black font-mono text-xs font-bold uppercase rounded-none hover:bg-[#e0e0e0] cursor-pointer"
          >
            {t('close')}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

// ─── Main Unified Dashboard Page ─────────────────────────────────────────────
export default function Dashboard() {
  const [bannerMsg, setBannerMsg] = useState('')
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [showBarcodeModal, setShowBarcodeModal] = useState(false)
  const [showFaceModal, setShowFaceModal] = useState(false)
  const [externalOpenTimetable, setExternalOpenTimetable] = useState(false)
  const { getAccessTokenSilently, user } = useAuth0()
  const { t, syncWithServer } = useLanguage()

  // Apply theme from localStorage on mount
  useEffect(() => {
    const savedTheme = localStorage.getItem('mirror_theme') || 'oled-black'
    document.documentElement.setAttribute('data-theme', savedTheme)
  }, [])

  // Sync language with server on user login
  useEffect(() => {
    if (user) {
      getAccessTokenSilently()
        .then(token => syncWithServer(token))
        .catch(() => {})
    }
  }, [user, getAccessTokenSilently, syncWithServer])

  // Emergency banner
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
    const interval = setInterval(fetchBanner, 30000)
    return () => clearInterval(interval)
  }, [])

  // Onboarding trigger: only pop up if user has NOT linked barcode and has not checked "Don't show this again"
  useEffect(() => {
    const checkOnboardingNeeded = async () => {
      if (localStorage.getItem('hide_onboarding_modal') === 'true') {
        return
      }

      let hasBarcode = false
      try {
        const token = await getAccessTokenSilently()
        const res = await fetch(`${API_URL}/api/users/me/barcode`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (res.ok) {
          const data = await res.json()
          hasBarcode = Boolean(data.barcode && data.barcode.trim())
        }
      } catch { /* silent */ }

      // Face is optional, so we only prompt onboarding if barcode is missing
      if (!hasBarcode) {
        setShowOnboarding(true)
      }
    }

    if (user) {
      checkOnboardingNeeded()
    }
  }, [user, getAccessTokenSilently])

  return (
    <div className="h-screen w-full flex flex-col bg-[#000000] text-white font-sans overflow-hidden relative">
      <Navbar />

      <main className="flex-1 flex flex-col relative z-10 min-h-0 overflow-hidden">
        {/* Top Emergency Notice Banner */}
        <AnimatePresence mode="wait">
          {bannerMsg && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="w-full bg-[#140a0a] border-b border-[#3b1212] px-6 py-2 flex items-center gap-3 text-xs text-[#fca5a5] shrink-0"
            >
              <span className="bg-[#ef4444] text-black font-mono font-bold text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-none shrink-0">
                NOTICE
              </span>
              <span className="truncate font-sans font-medium text-white">{bannerMsg}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 2-Column Unified Layout: Left = Notices, Right = Timetable */}
        <div className="grid grid-cols-1 md:grid-cols-[48%_52%] flex-1 min-h-0 overflow-hidden">
          {/* LEFT: NOTICES PANEL */}
          <section className="flex flex-col h-full min-h-0 bg-[#000000] border-r border-[#1c1c1c]">
            <DailyNoticesWidget widget={{}} />
          </section>

          {/* RIGHT: TIMETABLE & HERO PANEL */}
          <section className="flex flex-col p-6 md:p-8 h-full min-h-0 bg-[#000000] overflow-y-auto">
            <div className="flex-1 flex flex-col justify-center min-h-0 py-2">
              <TimetableWidget
                widget={{ data: { viewMode: 'today' } }}
                externalOpenSetup={externalOpenTimetable}
                onExternalCloseSetup={() => setExternalOpenTimetable(false)}
              />
            </div>

            {/* Bottom Footer Info */}
            <div className="pt-3 border-t border-[#1c1c1c] flex items-center justify-between text-[11px] font-mono text-[#666666] shrink-0 select-none">
              <div className="flex items-center gap-3">
                <Link to="/privacy" className="hover:text-white transition-colors">
                  {t('privacy')}
                </Link>
                <span>·</span>
                <Link to="/terms" className="hover:text-white transition-colors">
                  {t('terms')}
                </Link>
              </div>
              <div className="text-[10px] text-[#888888] font-mono uppercase tracking-wider">
                KING&apos;S HIGH SCHOOL SMART MIRROR
              </div>
            </div>
          </section>
        </div>
      </main>

      {/* Onboarding Pop-up Modal */}
      <OnboardingModal
        isOpen={showOnboarding}
        onClose={() => setShowOnboarding(false)}
        onOpenBarcode={() => setShowBarcodeModal(true)}
        onOpenFace={() => setShowFaceModal(true)}
        onOpenTimetable={() => setExternalOpenTimetable(true)}
      />

      {/* Modals triggerable from Onboarding */}
      <BarcodeCaptureModal
        isOpen={showBarcodeModal}
        onClose={() => setShowBarcodeModal(false)}
        onBarcodeSaved={() => setShowBarcodeModal(false)}
      />

      <FaceCaptureModal
        isOpen={showFaceModal}
        onClose={() => setShowFaceModal(false)}
        onCaptureComplete={() => {
          setShowFaceModal(false)
          window.location.reload()
        }}
      />
    </div>
  )
}
