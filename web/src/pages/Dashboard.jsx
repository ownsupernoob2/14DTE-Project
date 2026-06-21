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

  useEffect(() => {
    fetchWidgets()

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

  const fetchWidgets = async () => {
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch(`${API_URL}/api/dashboard/widgets`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        const fetchedWidgets = data || []
        
        // Normalize any old absolute coordinates to percentages!
        // We'll assume old coordinates were saved based on a standard 1280x800 web layout space.
        const normalized = fetchedWidgets.map(w => {
          const wNew = { ...w }
          if (w.x !== undefined && w.x > 100) {
            wNew.x = (w.x / 1280) * 100
          }
          if (w.y !== undefined && w.y > 100) {
            wNew.y = (w.y / 800) * 100
          }
          if (w.w !== undefined && w.w > 100) {
            wNew.w = (w.w / 1280) * 100
          }
          if (w.h !== undefined && w.h > 100) {
            wNew.h = (w.h / 800) * 100
          }
          return wNew
        })
        
        setWidgets(normalized)
        setSavedWidgets(normalized)
        setWidgetsLoaded(true)
        setErrorMsg('')
      } else {
        setWidgetsLoaded(true)
        setErrorMsg('Failed to load dashboard.')
      }
    } catch (e) {
      console.error(e)
      setWidgetsLoaded(true)
      setErrorMsg('The Smart Mirror server is offline, please try again later.')
    }
  }

  const addWidget = (type) => {
    const containerWidth = dimensions.width
    const containerHeight = dimensions.height
    
    // Type-specific default sizes matching DEFAULT_SIZES to avoid shrinking/covering content
    const defaults = {
      clock:     { w: 220, h: 100 },
      notices:   { w: 420, h: 340 },
      timetable: { w: 360, h: 320 },
      note:      { w: 220, h: 180 },
    }
    const size = defaults[type] || { w: 220, h: 160 }
    const widgetWidth = size.w
    const widgetHeight = size.h

    // Store as percentages (0-100) immediately
    const w_pct = (widgetWidth / containerWidth) * 100
    const h_pct = (widgetHeight / containerHeight) * 100

    // Search for a non-overlapping position
    let x_pct = 2 // start at 2% x
    let y_pct = 12 // start at 12% y (below navbar)
    
    const checkOverlapPct = (px, py, pw, ph) => {
      return widgets.some(w => {
        const margin = 0.05
        return (
          px + margin < w.x + w.w &&
          px + pw - margin > w.x &&
          py + margin < w.y + w.h &&
          py + ph - margin > w.y
        )
      })
    }

    let found = false
    for (let row = 0; row < 10 && !found; row++) {
      for (let col = 0; col < 10 && !found; col++) {
        const testX = 2 + col * (w_pct + 2)
        const testY = 12 + row * (h_pct + 2)
        
        if (testX + w_pct <= 98 && testY + h_pct <= 98) {
          if (!checkOverlapPct(testX, testY, w_pct, h_pct)) {
            x_pct = testX
            y_pct = testY
            found = true
          }
        }
      }
    }
    
    if (!found) {
      x_pct = 2 + Math.random() * 5
      y_pct = 12 + Math.random() * 5
    }

    const newWidget = {
      id: `new-${Date.now()}`,
      type,
      x: x_pct,
      y: y_pct,
      w: w_pct,
      h: h_pct,
    }

    setShowAddMenu(false)
    setWidgets([...widgets, newWidget])
  }

  const removeWidget = (id) => {
    setWidgets(widgets.filter((w) => w.id !== id))
  }

  const updateWidgetPosition = (id, x, y, allowOverlap = false) => {
    const containerWidth = dimensions.width
    const containerHeight = dimensions.height
    const x_pct = (x / containerWidth) * 100
    const y_pct = (y / containerHeight) * 100

    setWidgets((current) => {
      const target = current.find((w) => w.id === id)
      if (!target) return current

      if (!allowOverlap) {
        const wouldOverlap = current.some((w) => {
          if (w.id === id) return false
          return overlapsPct(x_pct, y_pct, target.w, target.h, w.x, w.y, w.w, w.h)
        })
        if (wouldOverlap) return current
      }

      return current.map((w) => (w.id === id ? { ...w, x: x_pct, y: y_pct } : w))
    })
  }

  const resolveWidgetOverlaps = (id) => {
    setWidgets((current) => {
      const target = current.find((w) => w.id === id)
      if (!target) return current

      const others = current.filter((w) => w.id !== id)
      const hasOverlap = others.some((w) =>
        overlapsPct(target.x, target.y, target.w, target.h, w.x, w.y, w.w, w.h)
      )
      if (!hasOverlap) return current

      const { x, y } = resolveOverlapPosition(target, others)
      return current.map((w) => (w.id === id ? { ...w, x, y } : w))
    })
  }

  const updateWidgetSize = (id, width, height) => {
    const containerWidth = dimensions.width
    const containerHeight = dimensions.height
    const w_pct = (width / containerWidth) * 100
    const h_pct = (height / containerHeight) * 100

    const target = widgets.find((w) => w.id === id)
    if (!target) return

    // Check if resizing would overlap with any other widget
    const wouldOverlap = widgets.some((w) => {
      if (w.id === id) return false
      const margin = 0.05
      return (
        target.x + margin < w.x + w.w &&
        target.x + w_pct - margin > w.x &&
        target.y + margin < w.y + w.h &&
        target.y + h_pct - margin > w.y
      )
    })

    if (wouldOverlap) return

    setWidgets(
      widgets.map((w) => (w.id === id ? { ...w, w: w_pct, h: h_pct } : w))
    )
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
      const res = await fetch(`${API_URL}/api/dashboard/widgets/bulk`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify(widgets)
      })
      if (res.ok) {
        setSavedWidgets(widgets)
        setErrorMsg('')
        return true
      } else {
        setErrorMsg('Failed to save layout')
        return false
      }
    } catch (e) {
      console.error(e)
      setErrorMsg('Failed to save layout')
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
    setShowAddMenu(false)
  }

  const undoLayout = () => {
    setWidgets(savedWidgets)
  }

  const hasUnsavedChanges = JSON.stringify(widgets) !== JSON.stringify(savedWidgets)
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
            onRemove={removeWidget}
            onMove={updateWidgetPosition}
            onDragEnd={resolveWidgetOverlaps}
            onResize={updateWidgetSize}
            onUpdateData={updateWidgetData}
            readonly={!isEditMode}
            containerWidth={dimensions.width}
            containerHeight={dimensions.height}
          />
        ))}

        {/* Modern Unified Customization Control Bar */}
        <div style={{
          position: 'absolute',
          bottom: 24,
          right: 24,
          zIndex: 100,
          display: 'flex',
          gap: '12px',
          alignItems: 'center'
        }}>
          {/* Unsaved changes indicators */}
          {hasUnsavedChanges && (
            <div className="glass-panel" style={{
              display: 'flex',
              gap: '8px',
              padding: '6px 12px',
              alignItems: 'center',
              borderRadius: '9999px',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              background: 'rgba(245, 158, 11, 0.08)'
            }}>
              <span style={{ fontSize: '0.72rem', fontWeight: 600, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Unsaved Layout</span>
              <button 
                className="notices-tab" 
                onClick={undoLayout}
                disabled={!isServerUp}
                style={{ padding: '4px 10px', fontSize: '0.72rem', background: 'rgba(255,255,255,0.06)' }}
              >
                Undo
              </button>
              <button 
                className="notices-tab active" 
                onClick={saveLayout}
                disabled={isSaving || !isServerUp}
                style={{ padding: '4px 10px', fontSize: '0.72rem', background: '#3b82f6' }}
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          )}

          {/* Add Widget Button (only in edit mode) */}
          {isEditMode && (
            <div style={{ position: 'relative' }}>
              <button
                className="modern-btn"
                onClick={() => isServerUp && setShowAddMenu(!showAddMenu)}
                disabled={!isServerUp}
                style={{
                  background: 'var(--glass-bg)',
                  color: 'white',
                  border: '1px solid var(--glass-border)',
                  padding: '10px 20px',
                  borderRadius: '9999px',
                  fontSize: '0.82rem',
                  letterSpacing: '0.05em',
                  boxShadow: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  width: 'auto'
                }}
              >
                <span>+ Add Widget</span>
              </button>
              
              {/* Add menu */}
              <AnimatePresence>
                {showAddMenu && (
                  <motion.div
                    initial={{ opacity: 0, y: 10, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 10, scale: 0.98 }}
                    transition={{ duration: 0.2 }}
                    className="glass-panel add-widget-menu"
                    style={{
                      position: 'absolute',
                      bottom: '50px',
                      right: '0',
                      width: '180px',
                      background: 'rgba(10, 10, 15, 0.95)',
                      padding: '8px',
                      borderRadius: '16px',
                      boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
                      border: '1px solid rgba(255,255,255,0.08)'
                    }}
                  >
                    {['clock', 'notices', 'timetable', 'note'].map((type) => (
                      <button
                        key={type}
                        onClick={() => addWidget(type)}
                        className="widget-menu-item"
                        style={{
                          padding: '8px 12px',
                          fontSize: '0.72rem',
                          borderRadius: '8px'
                        }}
                      >
                        {type === 'clock' ? 'Clock' : ''}
                        {type === 'notices' ? 'Daily Notices' : ''}
                        {type === 'timetable' ? 'Timetable' : ''}
                        {type === 'note' ? 'Note' : ''}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Toggle Edit Mode Button */}
          <button
            className="modern-btn"
            onClick={() => isEditMode ? handleDoneCustomizing() : setIsEditMode(true)}
            disabled={isEditMode && isSaving}
            style={{
              background: isEditMode ? 'var(--accent)' : 'rgba(255, 255, 255, 0.08)',
              color: 'white',
              border: isEditMode ? '1px solid var(--accent)' : '1px solid rgba(255, 255, 255, 0.15)',
              padding: '10px 20px',
              borderRadius: '9999px',
              fontSize: '0.82rem',
              letterSpacing: '0.05em',
              fontWeight: 600,
              boxShadow: isEditMode ? '0 0 15px var(--accent-glow)' : 'none',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              width: 'auto',
              opacity: (isEditMode && isSaving) ? 0.6 : 1,
            }}
          >
            <span>{isEditMode ? (isSaving ? 'Saving...' : 'Done') : 'Customize Layout'}</span>
          </button>
        </div>
      </div>

      <FaceCaptureModal isOpen={showFaceModal} onClose={() => setShowFaceModal(false)} />
    </div>
  )
}
