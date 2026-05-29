import { useState, useRef, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import Navbar from '../components/Navbar'
import WidgetContainer from '../components/WidgetContainer'
import { useServerStatus } from '../contexts/ServerStatusContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

export default function Dashboard() {
  const [widgets, setWidgets] = useState([])
  const [savedWidgets, setSavedWidgets] = useState([])
  const [showAddMenu, setShowAddMenu] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 800 })
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
        setErrorMsg('')
      } else {
        setErrorMsg('Failed to load dashboard.')
      }
    } catch (e) {
      console.error(e)
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

    const cols = Math.max(1, Math.floor(containerWidth / widgetWidth))
    const index = widgets.length
    const x = Math.min((index % cols) * widgetWidth + 24, containerWidth - widgetWidth)
    const y = Math.min(Math.floor(index / cols) * widgetHeight + 96, containerHeight - widgetHeight)

    // Store as percentages (0-100) immediately
    const x_pct = (x / containerWidth) * 100
    const y_pct = (y / containerHeight) * 100
    const w_pct = (widgetWidth / containerWidth) * 100
    const h_pct = (widgetHeight / containerHeight) * 100

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

  const updateWidgetPosition = (id, x, y) => {
    const containerWidth = dimensions.width
    const containerHeight = dimensions.height
    const x_pct = (x / containerWidth) * 100
    const y_pct = (y / containerHeight) * 100
    setWidgets(
      widgets.map((w) => (w.id === id ? { ...w, x: x_pct, y: y_pct } : w))
    )
  }

  const updateWidgetSize = (id, width, height) => {
    const containerWidth = dimensions.width
    const containerHeight = dimensions.height
    const w_pct = (width / containerWidth) * 100
    const h_pct = (height / containerHeight) * 100
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
      } else {
        setErrorMsg('Failed to save layout')
      }
    } catch (e) {
      console.error(e)
      setErrorMsg('Failed to save layout')
    } finally {
      setIsSaving(false)
    }
  }

  const undoLayout = () => {
    setWidgets(savedWidgets)
  }

  const hasUnsavedChanges = JSON.stringify(widgets) !== JSON.stringify(savedWidgets)

  return (
    <div className="dashboard-container">
      <Navbar />
      <div ref={containerRef} className="dashboard-canvas">
        <div className="dashboard-bg-gradient" />



        {/* Action Bar */}
        <AnimatePresence>
          {hasUnsavedChanges && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              style={{
                position: 'absolute',
                bottom: 20,
                left: 20,
                zIndex: 100,
                display: 'flex',
                gap: '10px'
              }}
            >
              <button 
                className="modern-btn modern-btn-outline" 
                onClick={undoLayout}
                disabled={!isServerUp}
                style={{ opacity: isServerUp ? 1 : 0.5, cursor: isServerUp ? 'pointer' : 'not-allowed', padding: '8px 16px', background: 'rgba(255,255,255,0.1)' }}
              >
                Undo
              </button>
              <button 
                className="modern-btn" 
                onClick={saveLayout}
                disabled={isSaving || !isServerUp}
                style={{ opacity: isServerUp ? 1 : 0.5, cursor: isServerUp ? 'pointer' : 'not-allowed', padding: '8px 16px', background: '#3b82f6', color: 'white', border: 'none' }}
              >
                {isSaving ? 'Saving...' : 'Save Layout'}
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {widgets.map((widget) => {
          return (
            <WidgetContainer
              key={widget.id}
              widget={widget}
              onRemove={removeWidget}
              onMove={updateWidgetPosition}
              onResize={updateWidgetSize}
              onUpdateData={updateWidgetData}
              containerWidth={dimensions.width}
              containerHeight={dimensions.height}
            />
          )
        })}

        <motion.button
          onClick={() => isServerUp && setShowAddMenu(!showAddMenu)}
          whileHover={isServerUp ? { scale: 1.05 } : {}}
          whileTap={isServerUp ? { scale: 0.95 } : {}}
          className="fab-btn"
          style={{ opacity: isServerUp ? 1 : 0.5, cursor: isServerUp ? 'pointer' : 'not-allowed' }}
        >
          +
        </motion.button>

        <AnimatePresence>
          {showAddMenu && (
            <motion.div
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.98 }}
              transition={{ duration: 0.2 }}
              className="glass-panel add-widget-menu"
            >
              {['clock', 'notices', 'timetable', 'note'].map((type) => (
                <button
                  key={type}
                  onClick={() => addWidget(type)}
                  className="widget-menu-item"
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
    </div>
  )
}
