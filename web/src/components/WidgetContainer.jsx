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
      className={`glass-panel widget-container ${isDragging ? 'dragging' : ''}`}
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
      <div className="widget-header">
        <span className="text-overline">
          {widget.type}
        </span>
        <button
          className="widget-close"
          onClick={() => onRemove(widget.id)}
        >
          ×
        </button>
      </div>
      <div className="widget-content">
        {widget.type === 'clock' && <div className="widget-clock">12:34 PM</div>}
        {widget.type === 'weather' && <div>72°F · Sunny</div>}
        {widget.type === 'calendar' && <div>Tuesday · April 24</div>}
        {widget.type === 'note' && (
          <textarea
            className="widget-textarea"
            placeholder="Type your note..."
          />
        )}
      </div>
    </motion.div>
  )
}
