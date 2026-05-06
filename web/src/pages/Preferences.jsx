import { useState, useRef, useCallback } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { motion } from 'framer-motion'
import Webcam from 'react-webcam'
import Navbar from '../components/Navbar'

export default function Preferences() {
  const { user, logout, getAccessTokenSilently } = useAuth0()
  const [showWebcam, setShowWebcam] = useState(false)
  const [capturedImage, setCapturedImage] = useState(null)
  const [uploadStatus, setUploadStatus] = useState('')
  const webcamRef = useRef(null)

  const capture = useCallback(() => {
    const imageSrc = webcamRef.current.getScreenshot()
    setCapturedImage(imageSrc)
  }, [webcamRef])

  const retake = () => {
    setCapturedImage(null)
    setUploadStatus('')
  }

  const saveFace = async () => {
    if (!capturedImage) return
    setUploadStatus('Uploading...')

    try {
      const token = await getAccessTokenSilently()
      const res = await fetch('http://localhost:8080/api/users/me/face', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ image: capturedImage })
      })

      if (res.ok) {
        setUploadStatus('Face successfully registered!')
        setTimeout(() => {
          setShowWebcam(false)
          setCapturedImage(null)
          setUploadStatus('')
        }, 2000)
      } else {
        setUploadStatus('Failed to register face.')
      }
    } catch (e) {
      console.error(e)
      setUploadStatus('Error connecting to server.')
    }
  }

  return (
    <div className="preferences-container">
      <Navbar />
      <div className="preferences-content">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="glass-panel preferences-card"
        >
          <h1 className="text-title">Preferences</h1>

          {user && (
            <section className="pref-section user-profile">
              <img
                src={user.picture}
                alt={user.name}
                className="profile-img"
              />
              <div>
                <h3 className="profile-name">{user.name}</h3>
                <p className="profile-email">{user.email}</p>
              </div>
            </section>
          )}

          <section className="pref-section pref-section-block">
            <h2 className="text-overline">Face Registration</h2>
            <p className="text-subtitle" style={{ fontSize: '0.85rem', marginBottom: '16px' }}>
              Register your face so the smart mirror can identify you and load your dashboard.
            </p>
            
            {!showWebcam ? (
              <button className="modern-btn" onClick={() => setShowWebcam(true)}>
                Register Face Scan
              </button>
            ) : (
              <div className="webcam-container" style={{ display: 'flex', flexDirection: 'column', gap: '16px', alignItems: 'center' }}>
                {!capturedImage ? (
                  <>
                    <Webcam
                      audio={false}
                      ref={webcamRef}
                      screenshotFormat="image/jpeg"
                      style={{ width: '100%', maxWidth: '400px', borderRadius: '8px' }}
                    />
                    <button className="modern-btn" onClick={capture}>Capture Photo</button>
                    <button className="modern-btn modern-btn-outline" onClick={() => setShowWebcam(false)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <img src={capturedImage} alt="Captured face" style={{ width: '100%', maxWidth: '400px', borderRadius: '8px' }} />
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button className="modern-btn" onClick={saveFace}>Save Face</button>
                      <button className="modern-btn modern-btn-outline" onClick={retake}>Retake</button>
                    </div>
                    {uploadStatus && <p style={{ color: uploadStatus.includes('Error') || uploadStatus.includes('Failed') ? '#ef4444' : '#10b981', fontSize: '0.875rem' }}>{uploadStatus}</p>}
                  </>
                )}
              </div>
            )}
          </section>

          <section className="pref-grid">
            <div className="pref-section">
              <h2 className="text-overline">Theme</h2>
              <div className="pref-options">
                <label className="pref-radio">
                  <input type="radio" name="theme" value="dark" defaultChecked />
                  Dark Mode
                </label>
                <label className="pref-radio">
                  <input type="radio" name="theme" value="light" />
                  Light Mode
                </label>
              </div>
            </div>

            <div className="pref-section">
              <h2 className="text-overline">Language</h2>
              <select
                defaultValue="en"
                className="pref-select"
              >
                <option value="en">English</option>
                <option value="es">Spanish</option>
                <option value="fr">French</option>
                <option value="de">German</option>
              </select>
            </div>
          </section>

          <section className="pref-section pref-section-block">
            <h2 className="text-overline">Account</h2>
            <button
              className="modern-btn modern-btn-outline logout-btn"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
            >
              Logout
            </button>
          </section>
        </motion.div>
      </div>
    </div>
  )
}
