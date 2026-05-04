import { useState, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Navbar from '../components/Navbar'
import WidgetContainer from '../components/WidgetContainer'

export default function Dashboard() {
  const [widgets, setWidgets] = useState([])
  const [showAddMenu, setShowAddMenu] = useState(false)
  const containerRef = useRef(null)
  const widgetIdRef = useRef(1)

  const addWidget = (type) => {
    const containerWidth = containerRef.current?.offsetWidth || 900
    const containerHeight = containerRef.current?.offsetHeight || 600
    const widgetWidth = 220
    const widgetHeight = 160
    const cols = Math.max(1, Math.floor(containerWidth / widgetWidth))
    const index = widgets.length
    const x = Math.min((index % cols) * widgetWidth + 24, containerWidth - widgetWidth)
    const y = Math.min(Math.floor(index / cols) * widgetHeight + 96, containerHeight - widgetHeight)

    const newWidget = {
      id: widgetIdRef.current++,
      type,
      x,
      y,
    }
    setWidgets([...widgets, newWidget])
    setShowAddMenu(false)
  }

  const removeWidget = (id) => {
    setWidgets(widgets.filter((w) => w.id !== id))
  }

  const updateWidgetPosition = (id, x, y) => {
    setWidgets(
      widgets.map((w) => (w.id === id ? { ...w, x, y } : w))
    )
  }

  return (
    <div className="relative min-h-screen bg-black text-white">
      <Navbar />
      <div ref={containerRef} className="relative h-screen w-screen overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.08),transparent_45%)]" />

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
          className="absolute bottom-8 right-8 z-40 flex h-14 w-14 items-center justify-center rounded-full border border-white/30 bg-white text-2xl font-semibold text-black shadow-glow"
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
              className="absolute bottom-28 right-8 z-40 w-48 rounded-2xl border border-white/10 bg-black/80 p-3 shadow-soft backdrop-blur"
            >
              {['clock', 'weather', 'calendar', 'note'].map((type) => (
                <button
                  key={type}
                  onClick={() => addWidget(type)}
                  className="mb-2 w-full rounded-xl border border-white/10 px-4 py-2 text-left text-xs uppercase tracking-[0.3em] text-white/80 transition hover:border-white/40 hover:text-white"
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
