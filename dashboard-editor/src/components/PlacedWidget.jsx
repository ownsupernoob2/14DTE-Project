import { useRef, useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth0 } from '@auth0/auth0-react'
import {
  cellOrigin, cellSpanSize, CELL_SIZE, CELL_GAP, COLS, ROWS, sizeClass,
} from '../utils/gridUtils.js'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

/* ── Widget accent colours ──────────────────────────────────── */
const META = {
  clock:     { label: 'Clock',         color: '#4f8ef7' },
  notices:   { label: 'Daily Notices', color: '#7c5af8' },
  timetable: { label: 'Timetable',     color: '#22c9a0' },
  note:      { label: 'Note',          color: '#f5a524' },
  weather:   { label: 'Weather',       color: '#06bcd4' },
}

/* ══════════════════════════════════════════════════
   CLOCK CONTENT
══════════════════════════════════════════════════ */
function ClockContent({ theme }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const date = now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })
  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '12px 16px', fontFamily: theme.fontFamily,
    }}>
      <div className="clock-time" style={{ color: theme.primary }}>{time}</div>
      <div className="clock-date" style={{ fontFamily: theme.fontFamily }}>{date}</div>
    </div>
  )
}

/* ══════════════════════════════════════════════════
   DAILY NOTICES CONTENT
══════════════════════════════════════════════════ */
const CAT_COLORS = {
  General:       '#94a3b8',
  Sports:        '#22c55e',
  Meetings:      '#8b5cf6',
  Academic:      '#3b82f6',
  Careers:       '#fbbf24',
  'Arts & Culture': '#f43f5e',
  Service:       '#14b8a6',
}

function NoticesContent({ theme }) {
  const [notices, setNotices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const today = new Date().toDateString()
        const cd = localStorage.getItem('notices_date')
        const cdata = localStorage.getItem('notices_data')
        if (cd === today && cdata) {
          if (!cancelled) { setNotices(JSON.parse(cdata)); setLoading(false) }
          return
        }
        const res = await fetch(`${API_URL}/api/notices`)
        if (!res.ok) throw new Error('Failed')
        const data = await res.json()
        if (!cancelled) {
          const list = Array.isArray(data) ? data : []
          setNotices(list)
          localStorage.setItem('notices_date', today)
          localStorage.setItem('notices_data', JSON.stringify(list))
          setLoading(false)
        }
      } catch (e) {
        if (!cancelled) { setError(e.message); setLoading(false) }
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (loading) return <Spinner />
  if (error)   return <ErrMsg msg={error} />
  if (notices.length === 0) return <Empty msg="No notices today" />

  return (
    <div className="inner-scroll" style={{ padding: '10px 12px' }}>
      <div className="section-hdr" style={{ color: theme.primary }}>Today's Notices</div>
      {notices.map((n, i) => {
        const cat   = n.category || 'General'
        const color = CAT_COLORS[cat] || '#94a3b8'
        const title = n.title || (n.notice || '').replace(/<[^>]*>/g, ' ').slice(0, 60)
        return (
          <div key={n.id || i} className="notice-item" style={{ borderLeftColor: color }}>
            <div className="notice-title">{title}</div>
            <div className="notice-meta">
              <span className="notice-badge" style={{
                background: `${color}18`,
                border: `1px solid ${color}35`,
                color,
              }}>
                {cat}
              </span>
              {n.contact && (
                <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{n.contact}</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ══════════════════════════════════════════════════
   TIMETABLE CONTENT
══════════════════════════════════════════════════ */
function TimetableContent({ theme }) {
  const { getAccessTokenSilently } = useAuth0()
  const [periods, setPeriods] = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [icsUrl,  setIcsUrl]  = useState(() => localStorage.getItem('timetable_ics_url') || '')

  useEffect(() => {
    if (icsUrl) return
    let cancelled = false
    getAccessTokenSilently().then(token =>
      fetch(`${API_URL}/api/timetable/ics`, { headers: { Authorization: `Bearer ${token}` } })
    ).then(r => r.ok ? r.json() : null)
     .then(d => { if (!cancelled && d?.ics_url) { localStorage.setItem('timetable_ics_url', d.ics_url); setIcsUrl(d.ics_url) } })
     .catch(() => {})
    return () => { cancelled = true }
  }, [icsUrl, getAccessTokenSilently])

  useEffect(() => {
    if (!icsUrl) { setLoading(false); return }
    let cancelled = false
    async function load() {
      try {
        const today = new Date().toDateString()
        const cd = localStorage.getItem('timetable_cache_date')
        const cdata = localStorage.getItem('timetable_cache_data')
        if (cd === today && cdata) {
          const parsed = JSON.parse(cdata)
          if (!cancelled) { setPeriods(parsed.periods || (Array.isArray(parsed) ? parsed : [])); setLoading(false) }
          return
        }
        const token = await getAccessTokenSilently()
        const res = await fetch(`${API_URL}/api/timetable`, { headers: { Authorization: `Bearer ${token}` } })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const list = Array.isArray(data) ? data : (data.periods || data.events || [])
        if (!cancelled) {
          setPeriods(list)
          localStorage.setItem('timetable_cache_date', today)
          localStorage.setItem('timetable_cache_data', JSON.stringify(data))
          setLoading(false)
        }
      } catch (e) {
        if (!cancelled) { setError(e.message); setLoading(false) }
      }
    }
    load()
    return () => { cancelled = true }
  }, [icsUrl, getAccessTokenSilently])

  if (loading) return <Spinner />
  if (!icsUrl) return (
    <div style={{ padding: 14, color: 'var(--text-muted)', fontSize: '0.78rem', lineHeight: 1.6 }}>
      Configure your timetable ICS URL in Settings.
    </div>
  )
  if (error)   return <ErrMsg msg={error} />
  if (periods.length === 0) return <Empty msg="No classes today" />

  const now = new Date()
  const nowMins = now.getHours() * 60 + now.getMinutes()

  function toMins(t) {
    if (!t) return -1
    const m = String(t).match(/(\d{1,2}):(\d{2})/)
    if (m) return parseInt(m[1]) * 60 + parseInt(m[2])
    return -1
  }

  return (
    <div className="inner-scroll" style={{ padding: '10px 12px' }}>
      <div className="section-hdr" style={{ color: theme.secondary }}>Today's Timetable</div>
      {periods.map((p, i) => {
        const start = toMins(p.start_time || p.start)
        const end   = toMins(p.end_time   || p.end)
        const isCurrent = start !== -1 && end !== -1 && nowMins >= start && nowMins < end
        const startStr = (p.start_time || p.start || '').slice(0, 5)
        const endStr   = (p.end_time   || p.end   || '').slice(0, 5)
        const timeStr  = startStr && endStr ? `${startStr} – ${endStr}` : startStr || endStr
        return (
          <div key={i} className={`period-row${isCurrent ? ' active-period' : ''}`}
               style={{ borderLeftColor: isCurrent ? theme.secondary : 'transparent' }}>
            <div className="period-time" style={{ color: isCurrent ? theme.secondary : 'var(--text-muted)' }}>
              {timeStr}
            </div>
            <div className="period-subject">{p.summary || p.subject || p.name || 'Class'}</div>
            {(p.location || p.room) && (
              <div className="period-room" style={{
                background: isCurrent ? `${theme.secondary}18` : 'rgba(255,255,255,0.05)',
                borderColor: isCurrent ? `${theme.secondary}30` : 'var(--border)',
                color: isCurrent ? theme.secondary : 'var(--text-muted)',
              }}>
                {p.location || p.room}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ══════════════════════════════════════════════════
   NOTE CONTENT
══════════════════════════════════════════════════ */
function NoteContent({ widget, onUpdateData, theme }) {
  const [text, setText] = useState(widget.data?.note || '')
  const handleChange = (e) => {
    setText(e.target.value)
    onUpdateData?.(widget.id, { note: e.target.value })
  }
  return (
    <div style={{ padding: '10px 14px', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className="section-hdr" style={{ color: theme.primary, marginBottom: 8 }}>Note</div>
      <textarea
        className="note-textarea"
        value={text}
        onChange={handleChange}
        placeholder="Type your note here…"
        style={{ fontFamily: theme.fontFamily }}
      />
    </div>
  )
}

/* ══════════════════════════════════════════════════
   WEATHER CONTENT (static placeholder)
══════════════════════════════════════════════════ */
function WeatherContent({ theme }) {
  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 6, padding: 12,
      fontFamily: theme.fontFamily,
    }}>
      <div className="weather-temp" style={{ color: theme.primary }}>18°</div>
      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 500 }}>Partly Cloudy</div>
      <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Auckland, NZ</div>
    </div>
  )
}

/* ── Shared helpers ─────────────────────────────── */
function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 0.9, ease: 'linear' }}
        style={{ width: 18, height: 18, border: '2px solid var(--border)', borderTopColor: 'var(--accent)', borderRadius: '50%' }}
      />
    </div>
  )
}
function ErrMsg({ msg }) {
  return <div style={{ padding: 14, fontSize: '0.75rem', color: '#f87171', lineHeight: 1.5 }}>{msg}</div>
}
function Empty({ msg }) {
  return <div style={{ padding: 14, fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>{msg}</div>
}

/* ══════════════════════════════════════════════════
   RESIZE HANDLE
══════════════════════════════════════════════════ */
function ResizeHandle({ onResizeDrag, onResizeEnd }) {
  return (
    <div
      className="resize-handle"
      onMouseDown={onResizeDrag}
      title="Drag to resize"
    >
      <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
        <circle cx="10" cy="10" r="1.5" fill="var(--accent)" />
        <circle cx="6"  cy="10" r="1.5" fill="var(--accent)" opacity="0.5"/>
        <circle cx="10" cy="6"  r="1.5" fill="var(--accent)" opacity="0.5"/>
      </svg>
    </div>
  )
}

/* ══════════════════════════════════════════════════
   PLACED WIDGET
══════════════════════════════════════════════════ */
export default function PlacedWidget({
  widget, theme,
  onDragMove, onDragEnd,
  onResizeDrag, onResizeEnd,
  onRemove, onUpdateData,
  gridRef,
}) {
  const [isDragging, setIsDragging] = useState(false)
  const [hovered,    setHovered]    = useState(false)

  // Compute position from grid cell data
  const origin = cellOrigin(widget.grid_x, widget.grid_y)
  const size   = cellSpanSize(widget.grid_width, widget.grid_height)
  const meta   = META[widget.type] || META.note
  const sc     = sizeClass(widget.grid_width, widget.grid_height)

  /* ── Drag to move ───────────────────── */
  const pointerDownRef = useRef(null)
  const isDraggingRef  = useRef(false)

  const handlePointerDown = useCallback((e) => {
    if (e.target.closest('.resize-handle') || e.target.closest('button') || e.target.closest('textarea')) return
    e.preventDefault()
    pointerDownRef.current = { x: e.clientX, y: e.clientY }
    isDraggingRef.current = false

    function onMove(ev) {
      const dx = ev.clientX - pointerDownRef.current.x
      const dy = ev.clientY - pointerDownRef.current.y
      if (!isDraggingRef.current && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
        isDraggingRef.current = true
        setIsDragging(true)
      }
      if (isDraggingRef.current) onDragMove(ev, widget.id)
    }
    function onUp(ev) {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      if (isDraggingRef.current) {
        setIsDragging(false)
        onDragEnd(widget.id)
      }
      isDraggingRef.current = false
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [widget.id, onDragMove, onDragEnd])

  /* ── Resize ─────────────────────────── */
  const handleResizeDown = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    function onMove(ev) { onResizeDrag(ev, widget.id) }
    function onUp()     { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp); onResizeEnd(widget.id) }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [widget.id, onResizeDrag, onResizeEnd])

  const content = {
    clock:     <ClockContent theme={theme} />,
    notices:   <NoticesContent theme={theme} />,
    timetable: <TimetableContent theme={theme} />,
    note:      <NoteContent widget={widget} onUpdateData={onUpdateData} theme={theme} />,
    weather:   <WeatherContent theme={theme} />,
  }[widget.type] || null

  return (
    <motion.div
      layout
      layoutId={widget.id}
      initial={{ opacity: 0, scale: 0.88 }}
      animate={{ opacity: 1, scale: 1, x: origin.x, y: origin.y }}
      exit={{ opacity: 0, scale: 0.84 }}
      transition={{ type: 'spring', stiffness: 380, damping: 32 }}
      className={`placed-widget ${sc}${isDragging ? ' is-dragging' : ''}`}
      style={{
        position: 'absolute', top: 0, left: 0,
        width: size.width, height: size.height,
        borderColor: isDragging ? meta.color : hovered ? 'var(--border-mid)' : 'var(--border)',
        zIndex: isDragging ? 300 : 1,
      }}
      onPointerDown={handlePointerDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Header bar */}
      <div className="widget-header" style={{ borderBottomColor: `${meta.color}22` }}>
        <div className="widget-type-label">
          <div className="widget-dot" style={{ background: meta.color }} />
          <span style={{ color: meta.color }}>{meta.label}</span>
          <span style={{
            fontSize: '0.56rem', color: 'var(--text-dim)',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid var(--border)',
            borderRadius: 4, padding: '1px 6px',
          }}>
            {widget.grid_width}×{widget.grid_height}
          </span>
        </div>

        <AnimatePresence>
          {hovered && (
            <motion.button
              key="rm"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              onClick={(e) => { e.stopPropagation(); onRemove(widget.id) }}
              style={{
                background: 'rgba(240,82,82,0.1)', border: '1px solid rgba(240,82,82,0.22)',
                color: '#f87171', borderRadius: 7, padding: '2px 9px',
                fontSize: '0.62rem', fontWeight: 700, cursor: 'pointer', flexShrink: 0,
              }}
            >
              Remove
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* Content body */}
      <div className="widget-body">
        {content}
      </div>

      {/* Resize handle */}
      <ResizeHandle onResizeDrag={handleResizeDown} onResizeEnd={() => {}} />
    </motion.div>
  )
}
