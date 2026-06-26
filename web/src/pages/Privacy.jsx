import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'

const PRIVACY_TEXT = `Privacy Policy & Terms of Use

Last updated: June 2026

1. Data Collection & Processing
Smart Mirror collects facial image data solely for the purpose of identifying registered users at the physical mirror terminal. Images are captured through your device camera during the registration process to construct a unique signature.

2. How Your Data Is Used
Your facial images are processed on our server to generate a 128-digit mathematical encoding (a numerical representation of your facial geometry). This encoding is used exclusively to identify you at the Smart Mirror. Raw images are permanently deleted from our servers immediately after the encoding is generated.

3. Secure Local Storage
Only the mathematical encoding derived from your face is stored. No raw photographs are retained. Encodings are stored securely and matched locally on a location-secure Raspberry Pi 5 device.

4. Data Sharing & Third Parties
We do not sell, share, or disclose your facial data or encodings to any third party. Your data is used solely within this Smart Mirror system.

5. Data Deletion (Instant Delete)
You may request deletion of your facial encoding at any time through your account settings using our instant-delete feature. Upon deletion, all related signatures are permanently erased.

6. Voluntary Participation & No Penalties
Using the mirror and personalising it by signing up is entirely optional. There are no penalties or academic impacts whatsoever if you choose not to use the mirror's face recognition feature. Alternative registration and identification methods (like barcode scanning) are available.`;

export default function Privacy() {
  const navigate = useNavigate()
  const [showGate, setShowGate] = useState(true)

  return (
    <div className="auth-container" style={{ padding: '24px', overflowY: 'auto', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="dashboard-bg-gradient" />

      {/* Parental Gate Modal */}
      <AnimatePresence>
        {showGate && (
          <motion.div
            className="fc-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{ zIndex: 10000 }}
          >
            <motion.div
              className="fc-modal"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              style={{ maxWidth: '480px', maxHeight: "500px", padding: '32px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}
            >
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: '16px' }}>
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
              </svg>
              <h2 className="fc-title" style={{ fontSize: '1.4rem', marginBottom: '16px', color: '#fff' }}>Parental Review Required</h2>

              <div className="glass-panel" style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', padding: '16px', borderRadius: '12px', marginBottom: '24px', width: '100%' }}>
                <p style={{ color: '#f87171', fontWeight: 'bold', fontSize: '1.02rem', margin: 0, lineHeight: 1.5 }}>
                  "If you are under 16, a parent/caregiver must review this notice."
                </p>
              </div>

              <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '28px' }}>
                This notice explains how the Smart Mirror protects student privacy and handles data. If you are under 16, please invite a parent or caregiver to read this with you.
              </p>

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', width: '100%' }}>
                <button
                  className="fc-btn fc-btn-outline"
                  onClick={() => navigate(-1)}
                  style={{ flex: 1 }}
                >
                  Go Back
                </button>
                <button
                  className="fc-btn"
                  onClick={() => setShowGate(false)}
                  style={{ flex: 1, background: 'var(--accent)' }}
                >
                  Review Notice
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="glass-panel"
        style={{
          width: '100%',
          maxWidth: '800px',
          padding: '40px',
          borderRadius: '24px',
          background: 'rgba(10, 10, 15, 0.85)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          boxShadow: '0 20px 50px rgba(0,0,0,0.4)',
          position: 'relative',
          margin: '40px 0'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h1 className="text-title" style={{ margin: 0, fontSize: '2rem' }}>Privacy &amp; Consent</h1>
            <p className="text-subtitle" style={{ margin: '4px 0 0 0' }}>Kings High School Smart Mirror System</p>
          </div>
          <button
            className="fc-btn fc-btn-outline"
            onClick={() => navigate(-1)}
            style={{ width: 'auto', padding: '8px 18px', fontSize: '0.85rem' }}
          >
            &larr; Back
          </button>
        </div>

        {/* Voluntary Notice */}
        <div className="glass-panel" style={{
          background: 'rgba(255, 255, 255, 0.03)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          padding: '20px',
          borderRadius: '16px',
          marginBottom: '32px'
        }}>
          <h3 style={{ margin: '0 0 8px 0', fontSize: '0.88rem', color: 'rgba(255,255,255,0.85)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Participation is Voluntary
          </h3>
          <p style={{ color: '#e2e8f0', fontSize: '0.92rem', lineHeight: 1.6, margin: 0, fontWeight: 500 }}>
            "Using the mirror/personalising it by signing up is entirely optional."
          </p>
          <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.82rem', marginTop: '6px', marginBottom: 0 }}>
            If you choose not to use the face recognition features, you will experience absolutely no penalties. Alternative methods for looking up timetable details (like barcode scanning) are fully supported.
          </p>
        </div>



        {/* Detailed Policy Text */}
        <h2 style={{ fontSize: '1.2rem', color: '#fff', marginBottom: '16px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '8px', fontWeight: 600 }}>
          Terms &amp; Conditions
        </h2>
        <div
          className="custom-terms-scroll"
          style={{
            height: '420px',
            overflowY: 'auto',
            padding: '20px',
            background: 'rgba(0, 0, 0, 0.2)',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            marginBottom: '32px'
          }}
        >
          <pre style={{
            whiteSpace: 'pre-wrap',
            fontFamily: 'inherit',
            fontSize: '0.85rem',
            color: 'rgba(255,255,255,0.7)',
            lineHeight: 1.6,
            margin: 0
          }}>
            {PRIVACY_TEXT}
          </pre>
        </div>

        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <button
            className="fc-btn"
            onClick={() => navigate(-1)}
            style={{ width: 'auto', minWidth: '160px', background: 'var(--accent)' }}
          >
            I Understand
          </button>
        </div>
      </motion.div>
    </div>
  )
}
