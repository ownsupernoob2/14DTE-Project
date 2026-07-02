import { motion } from 'framer-motion'

// SVG icons — no emojis
const ICONS = {
  clock: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  notices: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
    </svg>
  ),
  timetable: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  note: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  ),
  weather: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
    </svg>
  ),
}

const WIDGET_META = {
  clock:     { label: 'Clock',         color: '#4f8ef7', span: '2×1', desc: 'Live time & date' },
  notices:   { label: 'Daily Notices', color: '#7c5af8', span: '3×3', desc: 'School announcements' },
  timetable: { label: 'Timetable',     color: '#22c9a0', span: '3×2', desc: "Today's classes" },
  note:      { label: 'Note',          color: '#f5a524', span: '2×2', desc: 'Custom text pad' },
  weather:   { label: 'Weather',       color: '#06bcd4', span: '1×2', desc: 'Local conditions' },
}

function TrayCard({ type, onAdd }) {
  const m = WIDGET_META[type]
  return (
    <motion.div
      className="tray-card"
      whileTap={{ scale: 0.97 }}
      onClick={() => onAdd(type)}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 11 }}>
        <div style={{
          width: 38, height: 38, borderRadius: 11, flexShrink: 0,
          background: `${m.color}18`, border: `1.5px solid ${m.color}30`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: m.color,
        }}>
          {ICONS[type]}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.82rem', fontWeight: 700, marginBottom: 2, color: 'var(--text)' }}>
            {m.label}
          </div>
          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>{m.desc}</div>
        </div>
      </div>
      <div style={{ marginTop: 9, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{
          fontSize: '0.6rem', color: m.color, fontWeight: 700,
          background: `${m.color}12`, border: `1px solid ${m.color}28`,
          borderRadius: 9999, padding: '2px 8px', letterSpacing: '0.04em',
        }}>
          {m.span} cells
        </span>
        <span style={{ fontSize: '0.6rem', color: 'var(--text-dim)' }}>click to add</span>
      </div>
    </motion.div>
  )
}

export default function WidgetTray({ onAdd, onClear, widgetCount }) {
  return (
    <aside className="editor-tray">
      <div style={{ marginBottom: 18 }}>
        <div className="section-hdr" style={{ marginBottom: 4 }}>Widget Tray</div>
        <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: 1.55 }}>
          Click to add, then drag to position or resize.
        </p>
      </div>

      {Object.keys(WIDGET_META).map(type => (
        <TrayCard key={type} type={type} onAdd={onAdd} />
      ))}

      <div className="divider" />

      <motion.button
        className="btn btn-danger"
        style={{ width: '100%', justifyContent: 'center', fontSize: '0.75rem' }}
        onClick={onClear}
        disabled={widgetCount === 0}
        whileTap={{ scale: 0.97 }}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
        </svg>
        Clear all
      </motion.button>

      <div style={{
        marginTop: 18, background: 'rgba(79,142,247,0.05)',
        border: '1px solid rgba(79,142,247,0.14)',
        borderRadius: 12, padding: '11px 13px',
      }}>
        <div style={{ fontSize: '0.62rem', fontWeight: 700, color: 'var(--accent)', marginBottom: 6, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Grid Tips
        </div>
        <ul style={{ fontSize: '0.64rem', color: 'var(--text-muted)', lineHeight: 1.7, paddingLeft: 12 }}>
          <li>Drag header bar to move</li>
          <li>Drag corner handle to resize</li>
          <li>Widgets snap to grid cells</li>
          <li>Content scales with size</li>
        </ul>
      </div>
    </aside>
  )
}
