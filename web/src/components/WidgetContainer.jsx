import { useState, useRef, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import DailyNoticesWidget from './DailyNoticesWidget'
import TimetableWidget from './TimetableWidget'
import { useServerStatus } from '../contexts/ServerStatusContext'

const DEFAULT_SIZES = {
  clock:     { w: 220, h: 100 },
  notices:   { w: 420, h: 340 },
  timetable: { w: 360, h: 320 },
  note:      { w: 220, h: 200 },
}

const WIDGET_LIMITS = {
  clock:     { minW: 160, minH: 80,  maxW: 600, maxH: 300 },
  notices:   { minW: 300, minH: 200, maxW: 900, maxH: 700 },
  timetable: { minW: 250, minH: 200, maxW: 900, maxH: 750 },
  note:      { minW: 160, minH: 120, maxW: 600, maxH: 500 },
}

// Note expiry duration options
const EXPIRY_OPTIONS = [
  { label: 'No expiry', value: 0 },
  { label: '1 hour',    value: 60 * 60 * 1000 },
  { label: '4 hours',   value: 4 * 60 * 60 * 1000 },
  { label: '1 day',     value: 24 * 60 * 60 * 1000 },
];

function useNoteExpiry(expireAt) {
  const [expired, setExpired] = useState(false);
  const [minutesLeft, setMinutesLeft] = useState(null);

  useEffect(() => {
    if (!expireAt) { setExpired(false); setMinutesLeft(null); return; }
    const check = () => {
      const diff = new Date(expireAt) - Date.now();
      if (diff <= 0) {
        setExpired(true);
        setMinutesLeft(0);
      } else {
        setExpired(false);
        setMinutesLeft(Math.ceil(diff / 60000));
      }
    };
    check();
    const id = setInterval(check, 30000);
    return () => clearInterval(id);
  }, [expireAt]);

  return { expired, minutesLeft };
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

export default function WidgetContainer({ widget, onRemove, onMove, onDragEnd, onResize, onUpdateData, readonly = false, containerWidth = 1280, containerHeight = 800 }) {
  const [isDragging, setIsDragging] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const resizeStart = useRef(null)
  const widgetRef = useRef(null)
  const { isServerUp } = useServerStatus()
  const { expired, minutesLeft } = useNoteExpiry(
    widget.type === 'note' ? widget.data?.expireAt : null
  )

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

  const dragState = useRef({ active: false, offsetX: 0, offsetY: 0 })

  const handleHeaderPointerDown = useCallback((e) => {
    if (readonly) return
    if (!isServerUp) return
    if (e.button !== 0) return
    if (e.target.closest('.widget-close')) return
    e.preventDefault()
    e.stopPropagation()

    const header = e.currentTarget
    const rect = widgetRef.current.getBoundingClientRect()
    dragState.current = {
      active:  true,
      offsetX: e.clientX - rect.left,
      offsetY: e.clientY - rect.top,
    }
    setIsDragging(true)
    header.setPointerCapture(e.pointerId)

    const onPointerMove = (moveE) => {
      if (!dragState.current.active) return
      const container = widgetRef.current?.parentElement
      if (!container) return

      const cr = container.getBoundingClientRect()
      let nx = moveE.clientX - cr.left - dragState.current.offsetX
      let ny = moveE.clientY - cr.top - dragState.current.offsetY

      const maxX = Math.max(0, container.offsetWidth - widgetRef.current.offsetWidth)
      const maxY = Math.max(0, container.offsetHeight - widgetRef.current.offsetHeight)
      nx = Math.max(0, Math.min(nx, maxX))
      ny = Math.max(0, Math.min(ny, maxY))

      onMove(widget.id, nx, ny, true)
    }

    const onPointerUp = (upE) => {
      dragState.current.active = false
      setIsDragging(false)
      header.removeEventListener('pointermove', onPointerMove)
      header.removeEventListener('pointerup', onPointerUp)
      header.removeEventListener('pointercancel', onPointerUp)
      try { header.releasePointerCapture(upE.pointerId) } catch { /* already released */ }
      onDragEnd?.(widget.id)
    }

    header.addEventListener('pointermove', onPointerMove)
    header.addEventListener('pointerup', onPointerUp)
    header.addEventListener('pointercancel', onPointerUp)
  }, [readonly, isServerUp, widget.id, onMove, onDragEnd])

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

  // Hide expired notes on mirror
  if (readonly && widget.type === 'note' && expired) {
    return null;
  }

  return (
    <motion.div
      ref={widgetRef}
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ left: widgetX, top: widgetY, opacity: 1, scale: 1 }}
      transition={isDragging
        ? { duration: 0 }
        : { left: { type: 'spring', stiffness: 420, damping: 34 }, top: { type: 'spring', stiffness: 420, damping: 34 }, opacity: { duration: 0.2 }, scale: { duration: 0.2 } }}
      className={`glass-panel widget-container ${isDragging ? 'dragging' : ''} ${isResizing ? 'resizing' : ''} ${readonly ? 'readonly' : ''}`}
      style={{
        width: `${widgetW}px`,
        height: `${widgetH}px`,
        position: 'absolute',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        fontSize: `${14 * widgetScale}px`,
        ...(readonly ? { background: 'none', border: 'none', boxShadow: 'none' } : {})
      }}
    >
      {!readonly && (
        <div
          className="widget-header"
          style={{ cursor: isServerUp ? (isDragging ? 'grabbing' : 'grab') : 'not-allowed', touchAction: 'none' }}
          onPointerDown={handleHeaderPointerDown}
        >
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
              {widget.data?.text || widget.data || 'No note written.'}
              {minutesLeft !== null && minutesLeft <= 10 && minutesLeft > 0 && (
                <div style={{
                  marginTop: '8px',
                  fontSize: '0.72em',
                  color: 'rgba(251,191,36,0.8)',
                  borderTop: '1px solid rgba(255,255,255,0.08)',
                  paddingTop: '6px',
                  fontWeight: 600,
                }}>
                  Expires in {minutesLeft} min
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '8px' }}>
              <textarea
                className="widget-textarea"
                style={{ flex: 1 }}
                placeholder="Type your note..."
                value={(typeof widget.data === 'object' ? widget.data?.text : widget.data) || ''}
                onChange={(e) => {
                  const currentData = typeof widget.data === 'object' ? widget.data : {};
                  onUpdateData && onUpdateData(widget.id, { ...currentData, text: e.target.value });
                }}
              />
              {/* Expiry picker */}
              <div className="note-expiry-row">
                <span className="note-expiry-label">Expires:</span>
                <div className="note-expiry-btns">
                  {EXPIRY_OPTIONS.map(opt => {
                    const currentData = typeof widget.data === 'object' ? widget.data : {};
                    const currentExpiry = currentData.expireDuration || 0;
                    const isActive = currentExpiry === opt.value;
                    return (
                      <button
                        key={opt.label}
                        className={`note-expiry-btn ${isActive ? 'active' : ''}`}
                        onClick={() => {
                          const expireAt = opt.value > 0
                            ? new Date(Date.now() + opt.value).toISOString()
                            : null;
                          onUpdateData && onUpdateData(widget.id, {
                            ...currentData,
                            expireDuration: opt.value,
                            expireAt,
                          });
                        }}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
                {(() => {
                  const currentData = typeof widget.data === 'object' ? widget.data : {};
                  if (!currentData.expireAt) return null;
                  const diff = new Date(currentData.expireAt) - Date.now();
                  if (diff <= 0) return <span className="note-expiry-status expired">Expired</span>;
                  const mins = Math.ceil(diff / 60000);
                  const hrs = Math.floor(mins / 60);
                  const label = hrs >= 1 ? `${hrs}h ${mins % 60}m left` : `${mins}m left`;
                  return <span className="note-expiry-status">{label}</span>;
                })()}
              </div>
            </div>
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
