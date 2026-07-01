import { useState, useRef, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import Navbar from '../components/Navbar'
import WidgetContainer from '../components/WidgetContainer'
import FaceCaptureModal from '../components/FaceCaptureModal'
import { useServerStatus } from '../contexts/ServerStatusContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

const overlapsPct = (ax, ay, aw, ah, bx, by, bw, bh, margin = 0.05) => (
  ax + margin < bx + bw &&
  ax + aw - margin > bx &&
  ay + margin < by + bh &&
  ay + ah - margin > by
)

function resolveOverlapPosition(widget, others) {
  let { x, y, w, h } = widget
  const margin = 0.05

  for (let iter = 0; iter < 24; iter++) {
    let moved = false
    for (const other of others) {
      if (!overlapsPct(x, y, w, h, other.x, other.y, other.w, other.h, margin)) continue

      const pushRight  = (x + w) - other.x
      const pushLeft   = (other.x + other.w) - x
      const pushBottom = (y + h) - other.y
      const pushTop    = (other.y + other.h) - y
      const minPush = Math.min(pushRight, pushLeft, pushBottom, pushTop)

      if (minPush === pushRight) x = other.x - w - margin
      else if (minPush === pushLeft) x = other.x + other.w + margin
      else if (minPush === pushTop) y = other.y + other.h + margin
      else y = other.y - h - margin

      x = Math.max(0, Math.min(x, 100 - w))
      y = Math.max(0, Math.min(y, 100 - h))
      moved = true
    }
    if (!moved) break
  }

  return { x, y }
}

export default function Dashboard() {
  const [widgets, setWidgets] = useState([])
  const [savedWidgets, setSavedWidgets] = useState([])
  const [showAddMenu, setShowAddMenu] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [widgetsLoaded, setWidgetsLoaded] = useState(false)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 800 })
  const [isEditMode, setIsEditMode] = useState(false)
  const [showFaceModal, setShowFaceModal] = useState(false)
  const containerRef = useRef(null)
  const { getAccessTokenSilently } = useAuth0()
  const { isServerUp } = useServerStatus()

  const [currentLayout, setCurrentLayout] = useState('focus')
  const [savedLayout, setSavedLayout] = useState('focus')

  const PREMADE_LAYOUTS = {
    focus: [
      { id: 'clk-1', type: 'clock', x: 38, y: 5, w: 24, h: 14 },
      { id: 'tt-1', type: 'timetable', x: 2, y: 22, w: 46, h: 72 },
      { id: 'not-1', type: 'notices', x: 52, y: 22, w: 46, h: 72 }
    ],
    bulletin: [
      { id: 'not-1', type: 'notices', x: 2, y: 5, w: 58, h: 90 },
      { id: 'clk-1', type: 'clock', x: 64, y: 5, w: 34, h: 15 },
      { id: 'tt-1', type: 'timetable', x: 64, y: 23, w: 34, h: 72 }
    ],
    compact: [
      { id: 'clk-1', type: 'clock', x: 35, y: 15, w: 30, h: 15 },
      { id: 'tt-1', type: 'timetable', x: 15, y: 35, w: 70, h: 50, data: { viewMode: 'next' } }
    ]
  }

  useEffect(() => {
    fetchLayout()

    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight
        })
      }
    }

    // Measure container size on mount after initial render
    setTimeout(handleResize, 100)

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const fetchLayout = async () => {
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/layout`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        const layoutName = data.layout || 'focus'
        setCurrentLayout(layoutName)
        setSavedLayout(layoutName)
        setWidgets(PREMADE_LAYOUTS[layoutName] || PREMADE_LAYOUTS.focus)
        setWidgetsLoaded(true)
        setErrorMsg('')
      } else {
        setWidgetsLoaded(true)
        setErrorMsg('Failed to load layout.')
      }
    } catch (e) {
      console.error(e)
      setWidgetsLoaded(true)
      setErrorMsg('The Smart Mirror server is offline, please try again later.')
    }
  }

  const selectLayout = (layoutName) => {
    if (PREMADE_LAYOUTS[layoutName]) {
      setCurrentLayout(layoutName)
      setWidgets(PREMADE_LAYOUTS[layoutName])
    }
  }

  const updateWidgetData = (id, data) => {
    setWidgets(
      widgets.map((w) => (w.id === id ? { ...w, data } : w))
    )
  }

  const saveLayout = async () => {
    setIsSaving(true)
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/layout`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({ layout: currentLayout })
      })
      if (res.ok) {
        setSavedLayout(currentLayout)
        setErrorMsg('')
        return true
      } else {
        setErrorMsg('Failed to save layout selection')
        return false
      }
    } catch (e) {
      console.error(e)
      setErrorMsg('Failed to save layout selection')
      return false
    } finally {
      setIsSaving(false)
    }
  }

  const handleDoneCustomizing = async () => {
    if (hasUnsavedChanges) {
      await saveLayout()
    }
    setIsEditMode(false)
  }

  const undoLayout = () => {
    setCurrentLayout(savedLayout)
    setWidgets(PREMADE_LAYOUTS[savedLayout] || PREMADE_LAYOUTS.focus)
  }

  const hasUnsavedChanges = currentLayout !== savedLayout
  const hasFaceScan = !!localStorage.getItem('lastFaceScan')

  return (
    <div className="dashboard-container">
      <Navbar />
      <div ref={containerRef} className="dashboard-canvas">
        <div className="dashboard-bg-gradient" />



        {/* ── Empty state ─────────────────────────────────────────── */}
        {widgetsLoaded && widgets.length === 0 && !errorMsg && !isEditMode && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: 'easeOut' }}
            style={{
              position: 'absolute',
              top: '60px', left: 0, right: 0, bottom: 0,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              zIndex: 10,
            }}
          >
            <div style={{ width: 'min(440px, 88vw)', textAlign: 'center' }}>
              <p style={{
                color: 'rgba(148,163,184,0.75)',
                fontSize: '0.95rem',
                lineHeight: 1.65,
                marginBottom: '24px',
              }}>
                Your dashboard is empty. {hasFaceScan ? 'Configure widgets to design your layout.' : 'Register your face so the mirror can load your layout, or add widgets manually.'}
              </p>
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
                {!hasFaceScan && (
                  <button
                    className="modern-btn"
                    onClick={() => isServerUp && setShowFaceModal(true)}
                    disabled={!isServerUp}
                    style={{
                      background: 'var(--accent)',
                      color: 'white',
                      border: 'none',
                      padding: '10px 22px',
                      borderRadius: '9999px',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      cursor: isServerUp ? 'pointer' : 'not-allowed',
                      opacity: isServerUp ? 1 : 0.5,
                    }}
                  >
                    Register Face Scan
                  </button>
                )}
                <button
                  className="modern-btn"
                  onClick={() => setIsEditMode(true)}
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    color: 'rgba(148,163,184,0.9)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    padding: '10px 22px',
                    borderRadius: '9999px',
                    fontSize: '0.82rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  Add Widgets
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {widgets.map((widget) => (
          <WidgetContainer
            key={widget.id}
            widget={widget}
            onUpdateData={updateWidgetData}
            readonly={true}
            containerWidth={dimensions.width}
            containerHeight={dimensions.height}
          />
        ))}

        {/* Pre-made Layouts custom UI bar */}
        <div style={{
          position: 'absolute',
          bottom: 24,
          right: 24,
          zIndex: 100,
          display: 'flex',
          gap: '12px',
          alignItems: 'center'
        }}>
          {isEditMode ? (
            <div className="glass-panel" style={{
              display: 'flex',
              gap: '10px',
              padding: '8px 16px',
              alignItems: 'center',
              borderRadius: '9999px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              background: 'rgba(10, 10, 15, 0.92)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.5)'
            }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginRight: '6px' }}>
                SELECT LAYOUT:
              </span>
              {['focus', 'bulletin', 'compact'].map((layoutName) => (
                <button
                  key={layoutName}
                  onClick={() => selectLayout(layoutName)}
                  style={{
                    padding: '8px 16px',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    borderRadius: '9999px',
                    border: 'none',
                    cursor: 'pointer',
                    background: currentLayout === layoutName ? 'var(--accent)' : 'rgba(255,255,255,0.06)',
                    color: currentLayout === layoutName ? '#0f172a' : 'rgba(255,255,255,0.8)',
                    transition: 'all 0.25s ease'
                  }}
                >
                  {layoutName.toUpperCase()}
                </button>
              ))}

              <div style={{ width: '1px', height: '20px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }} />

              {hasUnsavedChanges && (
                <>
                  <button 
                    className="notices-tab" 
                    onClick={undoLayout}
                    style={{ padding: '6px 14px', fontSize: '0.78rem', background: 'rgba(255,255,255,0.06)' }}
                  >
                    Cancel
                  </button>
                  <button 
                    className="notices-tab active" 
                    onClick={saveLayout}
                    disabled={isSaving}
                    style={{ padding: '6px 14px', fontSize: '0.78rem', background: '#10b981', color: '#fff' }}
                  >
                    {isSaving ? 'Saving...' : 'Apply Layout'}
                  </button>
                </>
              )}

              {!hasUnsavedChanges && (
                <button
                  className="notices-tab active"
                  onClick={() => setIsEditMode(false)}
                  style={{ padding: '6px 14px', fontSize: '0.78rem', background: 'var(--accent)', color: '#0f172a' }}
                >
                  Close Options
                </button>
              )}
            </div>
          ) : (
            <button
              className="modern-btn"
              onClick={() => setIsEditMode(true)}
              style={{
                background: 'rgba(255, 255, 255, 0.08)',
                color: 'white',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                padding: '12px 24px',
                borderRadius: '9999px',
                fontSize: '0.82rem',
                letterSpacing: '0.05em',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <span>Change Premade Layout</span>
            </button>
          )}
        </div>
      </div>

      <FaceCaptureModal isOpen={showFaceModal} onClose={() => setShowFaceModal(false)} />
    </div>
  )
}
