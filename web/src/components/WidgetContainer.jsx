import { useState, useRef, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import DailyNoticesWidget from './DailyNoticesWidget'
import TimetableWidget from './TimetableWidget'
import { useServerStatus } from '../contexts/ServerStatusContext'

const DEFAULT_SIZES = {
  clock:     { w: 220, h: 100 },
  notices:   { w: 420, h: 340 },
  timetable: { w: 280, h: 200 },
  note:      { w: 220, h: 180 },
}

function ClockWidget() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="widget-clock">
      <div style={{ fontSize: '2rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
        {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
      <div style={{ fontSize: '0.82rem', opacity: 0.6, marginTop: '4px' }}>
        {now.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
      </div>
    </div>
  )
}

export default function WidgetContainer({ widget, onRemove, onMove, onResize, readonly = false }) {
  const [isDragging, setIsDragging] = useState(false)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isResizing, setIsResizing] = useState(false)
  const resizeStart = useRef(null)
  const widgetRef = useRef(null)
  const { isServerUp } = useServerStatus()

  const defaults = DEFAULT_SIZES[widget.type] || { w: 220, h: 160 }
  const widgetW = widget.w ?? defaults.w
  const widgetH = widget.h ?? defaults.h

  const handleMouseDown = (e) => {
    if (readonly) return
    if (!isServerUp) return
    if (e.target.closest('.widget-close') || e.target.closest('.widget-resize-handle')) return

    setIsDragging(true)
    const rect = widgetRef.current.getBoundingClientRect()
    setOffset({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }

  const handleMouseMove = (e) => {
    if (!isDragging) return

    const container = widgetRef.current.parentElement
    const newX = e.clientX - container.getBoundingClientRect().left - offset.x
    const newY = e.clientY - container.getBoundingClientRect().top - offset.y

    const maxX = Math.max(0, container.offsetWidth - widgetRef.current.offsetWidth)
    const maxY = Math.max(0, container.offsetHeight - widgetRef.current.offsetHeight)

    onMove(widget.id, Math.max(0, Math.min(newX, maxX)), Math.max(0, Math.min(newY, maxY)))
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  const handleResizeMouseDown = useCallback((e) => {
    if (readonly) return
    e.stopPropagation()
    e.preventDefault()
    setIsResizing(true)
    resizeStart.current = { x: e.clientX, y: e.clientY, w: widgetW, h: widgetH }

    const onMouseMove = (moveE) => {
      if (!resizeStart.current) return
      const dx = moveE.clientX - resizeStart.current.x
      const dy = moveE.clientY - resizeStart.current.y
      const newW = Math.max(160, resizeStart.current.w + dx)
      const newH = Math.max(80, resizeStart.current.h + dy)
      onResize(widget.id, newW, newH)
    }
    const onMouseUp = () => {
      setIsResizing(false)
      resizeStart.current = null
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }, [readonly, widgetW, widgetH, widget.id, onResize])

  return (
    <motion.div
      ref={widgetRef}
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2 }}
      className={`glass-panel widget-container ${isDragging ? 'dragging' : ''} ${isResizing ? 'resizing' : ''} ${readonly ? 'readonly' : ''}`}
      style={{
        left: `${widget.x}px`,
        top: `${widget.y}px`,
        width: `${widgetW}px`,
        height: `${widgetH}px`,
        position: 'absolute',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        ...(readonly ? { background: 'none', border: 'none', boxShadow: 'none' } : {})
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {!readonly && (
        <div className="widget-header" style={{ cursor: isServerUp ? 'grab' : 'not-allowed' }}>
          <span className="text-overline">{widget.type}</span>
          <button
            className="widget-close"
            onClick={() => isServerUp && onRemove(widget.id)}
            disabled={!isServerUp}
            style={{ opacity: isServerUp ? 1 : 0.5, cursor: isServerUp ? 'pointer' : 'not-allowed' }}
          >
            ×
          </button>
        </div>
      )}

      <div className="widget-content" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {widget.type === 'clock'     && <ClockWidget />}
        {widget.type === 'notices'   && <DailyNoticesWidget />}
        {widget.type === 'timetable' && <TimetableWidget />}
        {widget.type === 'note'      && (
          <textarea className="widget-textarea" placeholder="Type your note..." />
        )}
      </div>

      {/* Resize handle — bottom right corner */}
      {!readonly && (
        <div
          className="widget-resize-handle"
          onMouseDown={handleResizeMouseDown}
          title="Drag to resize"
        />
      )}
    </motion.div>
  )
}
