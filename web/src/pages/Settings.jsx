import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import Navbar from '../components/Navbar'
import FaceCaptureModal from '../components/FaceCaptureModal'
import BarcodeCaptureModal from '../components/BarcodeCaptureModal'
import LegacyCalendarLink from '../legacy/IcsTimetableLink'
import { useServerStatus } from '../contexts/ServerStatusContext'
import { useMe } from '../contexts/MeContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

export default function Settings() {
  const { user, logout, getAccessTokenSilently } = useAuth0()
  const [showFaceModal, setShowFaceModal] = useState(false)
  const [showBarcodeModal, setShowBarcodeModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showWipeConfirm, setShowWipeConfirm] = useState(false)
  const [isWiping, setIsWiping] = useState(false)
  const { isServerUp } = useServerStatus()
  const [isDeleting, setIsDeleting] = useState(false)

  const [studentID, setStudentID] = useState(null)
  const [isUnlinking, setIsUnlinking] = useState(false)

  const lastScan = localStorage.getItem('lastFaceScan')
  const scanTime = lastScan ? parseInt(lastScan, 10) : 0
  const isScanRecent = (Date.now() - scanTime) < 24 * 60 * 60 * 1000

  const hoursUntilUpdate = isScanRecent
    ? Math.ceil((24 * 60 * 60 * 1000 - (Date.now() - scanTime)) / (60 * 60 * 1000))
    : 0

  // 1-Year Face Re-Scan Expiry Notification:
  // Only triggers if user previously enrolled their face and > 365 days elapsed
  const oneYearMs = 365 * 24 * 60 * 60 * 1000
  const isScanExpired = Boolean(lastScan && (Date.now() - scanTime > oneYearMs))
  const [showYearExpiredModal, setShowYearExpiredModal] = useState(() => {
    return isScanExpired && !sessionStorage.getItem('year_rescan_dismissed')
  })

  const { me, isAdmin } = useMe()
  const hasBarcode = Boolean(studentID && studentID.trim())
  // The server knows whether a scan exists (an admin may have removed it).
  const hasFace = me ? Boolean(me.has_face) : Boolean(lastScan)

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

    if (isServerUp) {
      loadStudentID()
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

  const handleWipeAccountData = async () => {
    setIsWiping(true)
    try {
      const token = await getAccessTokenSilently().catch(() => '')
      if (token) {
        await fetch(`${API_URL}/api/users/me/data`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` }
        })
      }
    } catch { /* proceed with local storage wipe */ }

    // Clear all client cached preferences and data
    localStorage.removeItem('lastFaceScan')
    localStorage.removeItem('timetable_ics_url')
    localStorage.removeItem('timetable_cache_date')
    localStorage.removeItem('timetable_cache_data')
    localStorage.removeItem('notices_date')
    localStorage.removeItem('notices_data')
    localStorage.removeItem('notices_fetchedAt')
    localStorage.removeItem('notices_widget_config')
    localStorage.removeItem('mirror_theme')
    sessionStorage.clear()

    // Sign out to complete wipe
    logout({ logoutParams: { returnTo: window.location.origin } })
  }

  return (
    <div className="min-h-screen bg-[#000000] text-white flex flex-col font-mono select-none">
      <Navbar />

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-8 flex flex-col gap-8">
        {/* Header */}
        <header className="border-b border-[#1c1c1c] pb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#888888]">
              KING&apos;S HIGH SMART MIRROR · ACCOUNT SETTINGS
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight uppercase">
            ACCOUNT MANAGEMENT
          </h1>
          <p className="text-xs text-[#888888] mt-1.5 uppercase tracking-wider">
            CONFIGURE BIOMETRIC PROFILES, STUDENT BARCODES, AND TERMINAL ACCESS.
          </p>
        </header>

        {/* User Profile Info (No 'authenticated' badge) */}
        {user && (
          <div className="bg-[#0c0c0c] p-5 flex items-center justify-between gap-4 rounded-none border border-[#1a1a1a]">
            <div className="flex items-center gap-4">
              <img
                src={user.picture}
                alt={user.name}
                className="w-12 h-12 rounded-none object-cover grayscale"
              />
              <div>
                <h3 className="text-sm font-bold text-white uppercase">{user.name}</h3>
                <p className="text-xs text-[#888888]">{user.email}</p>
              </div>
            </div>
          </div>
        )}

        {/* Section: Student ID Barcode Link */}
        <section className="bg-[#0c0c0c] p-6 flex flex-col gap-4 rounded-none border border-[#1a1a1a]">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#1c1c1c] pb-4">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                STUDENT ID BARCODE
              </h2>
              <p className="text-xs text-[#888888] mt-1">
                Link your physical ID card barcode for rapid scan login and identity verification.
              </p>
            </div>

            {hasBarcode && (
              <span className="px-2.5 py-1 text-[10px] font-bold uppercase bg-[#15803d] text-white border border-[#22c55e] shrink-0">
                ✓ ACTIVE
              </span>
            )}
          </div>

          {hasBarcode ? (
            <div className="bg-[#000000] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 border border-[#1a1a1a]">
              <div>
                <span className="text-[10px] text-[#888888] uppercase block">
                  ACTIVE STUDENT ID
                </span>
                <span className="text-base font-bold text-white tracking-widest mt-0.5 block">
                  {studentID}
                </span>
              </div>

              <div className="flex items-center gap-2.5 shrink-0">
                <button
                  type="button"
                  onClick={() => setShowBarcodeModal(true)}
                  disabled={!isServerUp}
                  className="px-4 py-2 text-xs font-bold uppercase bg-[#141414] hover:bg-[#202020] border border-[#2e2e2e] text-white transition-colors cursor-pointer rounded-none"
                >
                  CHANGE ID
                </button>
                <button
                  type="button"
                  onClick={unlinkStudentID}
                  disabled={isUnlinking || !isServerUp}
                  className="px-4 py-2 text-xs font-bold uppercase bg-[#1c0808] hover:bg-[#2c0e0e] text-[#f87171] border border-[#4a1212] transition-colors cursor-pointer disabled:opacity-50 rounded-none"
                >
                  {isUnlinking ? '...' : 'UNLINK'}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#000000] p-4 border border-[#1a1a1a]">
              <div>
                <h4 className="text-xs font-bold text-white uppercase">
                  NO BARCODE LINKED YET
                </h4>
                <p className="text-xs text-[#888888] mt-1 leading-relaxed">
                  Scan the barcode on the back of your student ID card using your device webcam.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowBarcodeModal(true)}
                disabled={!isServerUp || studentID === null}
                className="px-5 py-2.5 bg-white text-black hover:bg-[#e0e0e0] text-xs font-bold uppercase transition-all cursor-pointer disabled:opacity-50 shrink-0 rounded-none"
              >
                {studentID === null ? 'CHECKING...' : 'LINK BARCODE'}
              </button>
            </div>
          )}
        </section>

        {/* Section: Biometric Face Recognition (Optional mentioned only once, no redundant how-it-works essay) */}
        <section className="bg-[#0c0c0c] p-6 flex flex-col gap-4 rounded-none border border-[#1a1a1a]">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#1c1c1c] pb-4">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                BIOMETRIC FACE RECOGNITION
              </h2>
              <p className="text-xs text-[#888888] mt-1">
                Enrolling your face enables touchless, automatic sign-in at the mirror terminal (optional).
              </p>
            </div>

            {hasFace && (
              <span className="px-2.5 py-1 text-[10px] font-bold uppercase bg-[#15803d] text-white border border-[#22c55e] shrink-0">
                ✓ ACTIVE
              </span>
            )}
          </div>

          {!hasBarcode ? (
            <div className="bg-[#000000] p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border border-[#1a1a1a]">
              <div>
                <h4 className="text-xs font-bold text-white uppercase">BARCODE LINK REQUIRED FIRST</h4>
                <p className="text-xs text-[#888888] mt-1 max-w-lg leading-relaxed">
                  To prevent misidentification, a physical Student ID barcode must be linked to your account before enrolling facial biometrics.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowBarcodeModal(true)}
                className="px-4 py-2.5 bg-white text-black hover:bg-[#e0e0e0] text-xs font-bold uppercase transition-all cursor-pointer shrink-0 rounded-none"
              >
                LINK BARCODE TO UNLOCK
              </button>
            </div>
          ) : isScanRecent ? (
            <div className="bg-[#000000] p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border border-[#1a1a1a]">
              <div>
                <strong className="text-xs font-bold text-white uppercase block">FACE PROFILE REGISTERED</strong>
                <p className="text-xs text-[#888888] mt-1 leading-relaxed">
                  Active model. Can be updated in {hoursUntilUpdate} hour{hoursUntilUpdate !== 1 ? 's' : ''}.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={isDeleting || !isServerUp}
                className="px-4 py-2 text-xs font-bold uppercase bg-[#1c0808] hover:bg-[#2c0e0e] text-[#f87171] border border-[#4a1212] transition-colors cursor-pointer shrink-0 rounded-none"
              >
                DELETE &amp; RE-SCAN
              </button>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#000000] p-4 border border-[#1a1a1a]">
              <div>
                <h4 className="text-xs font-bold text-white uppercase">
                  READY FOR FACE ENROLLMENT
                </h4>
                <p className="text-xs text-[#888888] mt-1 leading-relaxed">
                  Your Student ID barcode is verified. Click below to begin camera calibration.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowFaceModal(true)}
                disabled={!isServerUp}
                className="px-5 py-2.5 bg-white text-black hover:bg-[#e0e0e0] text-xs font-bold uppercase transition-all cursor-pointer disabled:opacity-50 shrink-0 rounded-none"
              >
                {isServerUp ? 'REGISTER FACE' : 'SERVER OFFLINE'}
              </button>
            </div>
          )}
        </section>

        {/* Section: Administration (Admin only) */}
        {isAdmin && (
          <section className="bg-[#0c0c0c] p-6 flex flex-col gap-4 rounded-none border border-[#1a1a1a]">
            <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-3">
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                ADMINISTRATION &amp; A/B CONTROL
              </h2>
              <span className="px-2 py-0.5 text-[9px] font-bold uppercase bg-white text-black">
                SUPERUSER
              </span>
            </div>

            <p className="text-xs text-[#888888] leading-relaxed uppercase">
              ACCESS A/B TESTING OBSERVATORY, TELEMETRY, AND GESTURE ANALYTICS.
            </p>

            <div className="pt-2">
              <Link
                to="/admin"
                className="inline-block px-5 py-2.5 bg-white text-black hover:bg-[#e0e0e0] text-xs font-bold uppercase tracking-wider transition-all cursor-pointer rounded-none"
              >
                OPEN ADMIN ANALYTICS →
              </Link>
            </div>
          </section>
        )}

        {/* Section: Centered Sign Out and Long Wipe Account Data Buttons */}
        <section className="bg-[#0c0c0c] p-8 flex flex-col items-center gap-4 rounded-none border border-[#1a1a1a] text-center">
          <div className="w-full border-b border-[#1c1c1c] pb-3 mb-2">
            <h2 className="text-xs uppercase font-bold text-[#888888] tracking-widest">
              SESSION &amp; ACCOUNT ACTIONS
            </h2>
          </div>

          <div className="w-full flex flex-col items-center gap-3">
            {/* Long Centered Sign Out Button (Secondary Red Outline Style) */}
            <button
              type="button"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
              className="w-full max-w-md mx-auto py-3 px-6 bg-transparent text-[#ef4444] border-2 border-[#ef4444] hover:bg-[#ef4444]/10 text-xs font-mono font-bold uppercase tracking-wider transition-all cursor-pointer rounded-none flex items-center justify-center gap-2"
            >
              <span className="material-symbols-outlined text-sm">logout</span>
              <span>SIGN OUT</span>
            </button>

            {/* Long Centered Wipe Account Data Button (Solid Red Danger Style) */}
            <button
              type="button"
              onClick={() => setShowWipeConfirm(true)}
              className="w-full max-w-md mx-auto py-3.5 px-6 bg-[#dc2626] hover:bg-[#b91c1c] text-white text-xs font-mono font-bold uppercase tracking-wider transition-all cursor-pointer rounded-none flex items-center justify-center gap-2 shadow-lg"
            >
              <span className="material-symbols-outlined text-sm">delete_forever</span>
              <span>WIPE ACCOUNT DATA</span>
            </button>
          </div>
        </section>

        {/* Archived fallback: the old calendar-link timetable, kept out of the way */}
        <LegacyCalendarLink disabled={!isServerUp} />
      </main>

      {/* Face & Barcode Capture Modals */}
      <BarcodeCaptureModal
        isOpen={showBarcodeModal}
        onClose={() => setShowBarcodeModal(false)}
        onBarcodeSaved={(code) => {
          setStudentID(code)
          setShowBarcodeModal(false)
        }}
      />

      <FaceCaptureModal
        isOpen={showFaceModal}
        onClose={() => setShowFaceModal(false)}
        onCaptureComplete={() => {
          setShowFaceModal(false)
          window.location.reload()
        }}
      />

      {/* Delete Face Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm">
          <div className="bg-[#0a0a0a] border border-[#222222] p-6 max-w-md w-full flex flex-col gap-4 text-white font-mono rounded-none">
            <h3 className="text-sm font-bold text-white uppercase">
              CONFIRM FACE BIOMETRIC DELETION
            </h3>
            <p className="text-xs text-[#888888] leading-relaxed">
              Are you sure you want to delete your registered biometric face scan? This will remove your face embeddings from the server.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 border border-[#222222] text-[#888888] hover:text-white text-xs uppercase font-bold rounded-none cursor-pointer"
              >
                CLOSE
              </button>
              <button
                type="button"
                onClick={confirmDeleteFace}
                disabled={isDeleting}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-xs uppercase font-bold rounded-none cursor-pointer"
              >
                {isDeleting ? '...' : 'DELETE & RE-SCAN'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Wipe All Account Data Confirmation Modal */}
      {showWipeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md">
          <div className="bg-[#0a0a0a] border border-[#441111] p-6 max-w-md w-full flex flex-col gap-4 text-white font-mono rounded-none shadow-2xl">
            <div className="flex items-center gap-2 text-red-500">
              <span className="material-symbols-outlined text-2xl">warning</span>
              <h3 className="text-sm font-bold uppercase tracking-wider">
                CONFIRM COMPLETE ACCOUNT DATA WIPE
              </h3>
            </div>
            <p className="text-xs text-[#a0a0a0] leading-relaxed">
              Are you sure you want to wipe all account data? This will permanently delete your facial biometric embeddings from the mirror server, unlink your Student ID barcode, and clear timetable configuration. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3 pt-3 border-t border-[#1a1a1a]">
              <button
                type="button"
                onClick={() => setShowWipeConfirm(false)}
                disabled={isWiping}
                className="px-4 py-2 border border-[#222222] text-[#888888] hover:text-white text-xs uppercase font-bold rounded-none cursor-pointer"
              >
                CANCEL
              </button>
              <button
                type="button"
                onClick={handleWipeAccountData}
                disabled={isWiping}
                className="px-5 py-2.5 bg-[#dc2626] hover:bg-[#b91c1c] text-white text-xs uppercase font-bold rounded-none cursor-pointer transition-colors"
              >
                {isWiping ? 'WIPING DATA...' : 'YES, WIPE ALL DATA'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 1-Year Face Re-Scan Expiry Notification Modal */}
      {showYearExpiredModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm">
          <div className="bg-[#0a0a0a] border border-[#333333] p-6 max-w-md w-full flex flex-col gap-4 text-white font-mono rounded-none shadow-2xl">
            <div className="flex items-center gap-2 text-amber-400">
              <span className="material-symbols-outlined text-2xl">update</span>
              <h3 className="text-sm font-bold uppercase tracking-wider">
                BIOMETRICS UPDATE RECOMMENDED
              </h3>
            </div>
            <p className="text-xs text-[#b0b0b0] leading-relaxed">
              It has been over 1 year since your facial profile was scanned. Facial characteristics evolve over time. Re-scanning your face keeps touchless mirror recognition fast and accurate.
            </p>
            <div className="flex justify-end gap-3 pt-3 border-t border-[#1a1a1a]">
              <button
                type="button"
                onClick={() => {
                  sessionStorage.setItem('year_rescan_dismissed', '1')
                  setShowYearExpiredModal(false)
                }}
                className="px-4 py-2 border border-[#222222] text-[#888888] hover:text-white text-xs uppercase font-bold rounded-none cursor-pointer"
              >
                REMIND ME LATER
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowYearExpiredModal(false)
                  setShowFaceModal(true)
                }}
                className="px-5 py-2.5 bg-white text-black hover:bg-[#e0e0e0] text-xs uppercase font-bold rounded-none cursor-pointer transition-colors"
              >
                RE-SCAN NOW
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
