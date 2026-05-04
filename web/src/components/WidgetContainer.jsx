import { useState, useRef } from 'react'
import { motion } from 'framer-motion'

export default function WidgetContainer({ widget, onRemove, onMove }) {
  const [isDragging, setIsDragging] = useState(false)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const widgetRef = useRef(null)

  const handleMouseDown = (e) => {
    if (e.target.closest('.widget-close')) return
    
    setIsDragging(true)
    const rect = widgetRef.current.getBoundingClientRect()
    setOffset({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    })
  }

  const handleMouseMove = (e) => {
    if (!isDragging) return

    const container = widgetRef.current.parentElement
    const newX = e.clientX - container.getBoundingClientRect().left - offset.x
    const newY = e.clientY - container.getBoundingClientRect().top - offset.y

    // Keep widget in bounds
    const maxX = Math.max(0, container.offsetWidth - widgetRef.current.offsetWidth)
    const maxY = Math.max(0, container.offsetHeight - widgetRef.current.offsetHeight)

    const constrainedX = Math.max(0, Math.min(newX, maxX))
    const constrainedY = Math.max(0, Math.min(newY, maxY))

    onMove(widget.id, constrainedX, constrainedY)
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  return (
    <motion.div
      ref={widgetRef}
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2 }}
      className={`absolute rounded-2xl border border-white/10 bg-mirror-gray/90 p-4 text-white shadow-soft backdrop-blur ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
      style={{
        left: `${widget.x}px`,
        top: `${widget.y}px`,
        width: '220px',
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <div className="mb-3 flex items-center justify-between border-b border-white/10 pb-2">
        <span className="text-xs uppercase tracking-[0.3em] text-white/70">
          {widget.type}
        </span>
        <button
          className="text-lg text-white/60 transition hover:text-white"
          onClick={() => onRemove(widget.id)}
        >
          ×
        </button>
      </div>
      <div className="text-sm text-white/80">
        {widget.type === 'clock' && <div>12:34 PM</div>}
        {widget.type === 'weather' && <div>72°F · Sunny</div>}
        {widget.type === 'calendar' && <div>Tuesday · April 24</div>}
        {widget.type === 'note' && (
          <textarea
            className="h-20 w-full resize-none rounded-lg border border-white/10 bg-black/40 p-2 text-sm text-white outline-none"
            placeholder="Type your note..."
          />
        )}
      </div>
    </motion.div>
  )
}
