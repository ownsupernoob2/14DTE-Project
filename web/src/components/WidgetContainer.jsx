import { useState, useRef, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import DailyNoticesWidget from './DailyNoticesWidget'
import TimetableWidget from './TimetableWidget'
import { useServerStatus } from '../contexts/ServerStatusContext'

const DEFAULT_SIZES = {
  clock:     { w: 220, h: 100 },
  notices:   { w: 420, h: 340 },
  timetable: { w: 360, h: 320 },
  note:      { w: 220, h: 180 },
}

const WIDGET_LIMITS = {
  clock:     { minW: 160, minH: 80,  maxW: 600, maxH: 300 },
  notices:   { minW: 300, minH: 200, maxW: 900, maxH: 700 },
  timetable: { minW: 250, minH: 200, maxW: 900, maxH: 750 },
  note:      { minW: 160, minH: 100, maxW: 600, maxH: 500 },
}

function ClockWidget() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="widget-clock">
      <div style={{ fontSize: '2.4em', fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1 }}>
        {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
      <div style={{ fontSize: '0.8em', opacity: 0.6, marginTop: '0.3em', letterSpacing: '0.02em' }}>
        {now.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
      </div>
    </div>
  )
}

export default function WidgetContainer({ widget, onRemove, onMove, onResize, onUpdateData, readonly = false, containerWidth = 1280, containerHeight = 800 }) {
  const [isDragging, setIsDragging] = useState(false)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isResizing, setIsResizing] = useState(false)
  const resizeStart = useRef(null)
  const widgetRef = useRef(null)
  const { isServerUp } = useServerStatus()

  const defaults = DEFAULT_SIZES[widget.type] || { w: 220, h: 160 }
  const limits = WIDGET_LIMITS[widget.type] || { minW: 160, minH: 80, maxW: 800, maxH: 600 }
  
  // Convert percentage (0-100) back to pixels, or use pixels directly if absolute (backward compatibility)
  const rawW = widget.w !== undefined ? (widget.w > 100 ? widget.w : (widget.w / 100) * containerWidth) : defaults.w
  const rawH = widget.h !== undefined ? (widget.h > 100 ? widget.h : (widget.h / 100) * containerHeight) : defaults.h

  // Enforce widget size limits
  const widgetW = Math.max(limits.minW, Math.min(limits.maxW, rawW))
  const widgetH = Math.max(limits.minH, Math.min(limits.maxH, rawH))

  const widgetX = widget.x !== undefined ? (widget.x > 100 ? widget.x : (widget.x / 100) * containerWidth) : 24
  const widgetY = widget.y !== undefined ? (widget.y > 100 ? widget.y : (widget.y / 100) * containerHeight) : 96

  // Calculate dynamic scale factor based on widget dimensions vs default size
  // Use a gentler scale that prevents text from overflowing the container
  const scaleW = widgetW / defaults.w
  const scaleH = widgetH / defaults.h
  const widgetScale = Math.max(0.5, Math.min(2.5, Math.min(scaleW, scaleH) * 0.9))

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
      
      const newW = Math.max(limits.minW, Math.min(limits.maxW, resizeStart.current.w + dx))
      const newH = Math.max(limits.minH, Math.min(limits.maxH, resizeStart.current.h + dy))
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
  }, [readonly, widgetW, widgetH, widget.id, onResize, limits])

  return (
    <motion.div
      ref={widgetRef}
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2 }}
      className={`glass-panel widget-container ${isDragging ? 'dragging' : ''} ${isResizing ? 'resizing' : ''} ${readonly ? 'readonly' : ''}`}
      style={{
        left: `${widgetX}px`,
        top: `${widgetY}px`,
        width: `${widgetW}px`,
        height: `${widgetH}px`,
        position: 'absolute',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        fontSize: `${14 * widgetScale}px`,
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

      {/* widget-content: no extra padding for clock/notices/timetable — they self-manage */}
      <div 
        className="widget-content" 
        style={{ 
          flex: 1, 
          overflowY: widget.type === 'clock' ? 'hidden' : 'auto', 
          minHeight: 0,
          padding: widget.type === 'note' ? '12px 14px' : (widget.type === 'clock' ? '0' : undefined)
        }}
      >
        {widget.type === 'clock'     && <ClockWidget />}
        {widget.type === 'notices'   && (
          <DailyNoticesWidget 
            widget={widget}
            onUpdateData={(data) => onUpdateData && onUpdateData(widget.id, data)}
            readonly={readonly}
          />
        )}
        {widget.type === 'timetable' && (
          <TimetableWidget 
            widget={widget} 
            onUpdateData={(data) => onUpdateData && onUpdateData(widget.id, data)} 
            readonly={readonly}
          />
        )}
        {widget.type === 'note'      && (
          readonly ? (
            <div 
              className="widget-note-view" 
              style={{ 
                whiteSpace: 'pre-wrap', 
                wordBreak: 'break-word', 
                height: '100%', 
                width: '100%',
                overflowY: 'auto',
                fontSize: '0.95em',
                lineHeight: 1.5,
              }}
            >
              {widget.data || 'No note written.'}
            </div>
          ) : (
            <textarea
              className="widget-textarea"
              placeholder="Type your note..."
              value={widget.data || ''}
              onChange={(e) => onUpdateData && onUpdateData(widget.id, e.target.value)}
            />
          )
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
