import { useState, useRef } from 'react'
import '../styles/widget.css'

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
    <div
      ref={widgetRef}
      className={`widget ${widget.type} ${isDragging ? 'dragging' : ''}`}
      style={{
        position: 'absolute',
        left: `${widget.x}px`,
        top: `${widget.y}px`,
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <div className="widget-header">
        <span className="widget-title">{widget.type.charAt(0).toUpperCase() + widget.type.slice(1)}</span>
        <button
          className="widget-close"
          onClick={() => onRemove(widget.id)}
        >
          ×
        </button>
      </div>
      <div className="widget-content">
        {widget.type === 'clock' && <div>🕐 12:34 PM</div>}
        {widget.type === 'weather' && <div>☀️ 72°F, Sunny</div>}
        {widget.type === 'calendar' && <div>📅 Tuesday, April 24</div>}
        {widget.type === 'note' && <textarea placeholder="Type your note..."></textarea>}
      </div>
    </div>
  )
}
