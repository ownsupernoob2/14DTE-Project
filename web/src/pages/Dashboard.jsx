import { useState, useRef, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import Navbar from '../components/Navbar'
import WidgetContainer from '../components/WidgetContainer'

export default function Dashboard() {
  const [widgets, setWidgets] = useState([])
  const [showAddMenu, setShowAddMenu] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const containerRef = useRef(null)
  const { getAccessTokenSilently } = useAuth0()

  useEffect(() => {
    fetchWidgets()
  }, [])

  const fetchWidgets = async () => {
    try {
      const token = await getAccessTokenSilently()
      const res = await fetch('http://localhost:8080/api/dashboard/widgets', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setWidgets(data || [])
        setErrorMsg('')
      } else {
        setErrorMsg('The Smart Mirror server is offline, please try again later.')
      }
    } catch (e) {
      console.error(e)
      setErrorMsg('The Smart Mirror server is offline, please try again later.')
    }
  }

  const addWidget = async (type) => {
    const containerWidth = containerRef.current?.offsetWidth || 900
    const containerHeight = containerRef.current?.offsetHeight || 600
    const widgetWidth = 220
    const widgetHeight = 160
    const cols = Math.max(1, Math.floor(containerWidth / widgetWidth))
    const index = widgets.length
    const x = Math.min((index % cols) * widgetWidth + 24, containerWidth - widgetWidth)
    const y = Math.min(Math.floor(index / cols) * widgetHeight + 96, containerHeight - widgetHeight)

    const newWidget = {
      id: `new-${Date.now()}`,
      type,
      x,
      y,
    }

    setShowAddMenu(false)
    setWidgets([...widgets, newWidget])

    try {
      const token = await getAccessTokenSilently()
      const res = await fetch('http://localhost:8080/api/dashboard/widgets', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({ type, x, y })
      })
      if (res.ok) {
        const savedWidget = await res.json()
        setWidgets(prev => prev.map(w => w.id === newWidget.id ? savedWidget : w))
      }
    } catch (e) {
      console.error(e)
    }
  }

  const removeWidget = async (id) => {
    setWidgets(widgets.filter((w) => w.id !== id))
    try {
      const token = await getAccessTokenSilently()
      await fetch(`http://localhost:8080/api/dashboard/widgets/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      })
    } catch (e) {
      console.error(e)
    }
  }

  const updateWidgetPosition = async (id, x, y) => {
    const widgetToUpdate = widgets.find(w => w.id === id)
    if (!widgetToUpdate) return

    setWidgets(
      widgets.map((w) => (w.id === id ? { ...w, x, y } : w))
    )

    try {
      const token = await getAccessTokenSilently()
      await fetch(`http://localhost:8080/api/dashboard/widgets/${id}`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({ ...widgetToUpdate, x, y })
      })
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="dashboard-container">
      <Navbar />
      <div ref={containerRef} className="dashboard-canvas">
        <div className="dashboard-bg-gradient" />

        {errorMsg && (
          <div className="error-banner" style={{ background: 'red', color: 'white', padding: '10px', textAlign: 'center', position: 'absolute', top: 0, left: 0, right: 0, zIndex: 1000 }}>
            {errorMsg}
          </div>
        )}

        {widgets.map((widget) => (
          <WidgetContainer
            key={widget.id}
            widget={widget}
            onRemove={removeWidget}
            onMove={updateWidgetPosition}
          />
        ))}

        <motion.button
          onClick={() => setShowAddMenu(!showAddMenu)}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="fab-btn"
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
              {['clock', 'weather', 'calendar', 'note'].map((type) => (
                <button
                  key={type}
                  onClick={() => addWidget(type)}
                  className="widget-menu-item"
                >
                  {type}
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
