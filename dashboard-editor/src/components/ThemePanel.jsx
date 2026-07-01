import { useRef } from 'react'
import { motion } from 'framer-motion'

const FONT_OPTIONS = [
  { value: 'Outfit',            label: 'Outfit'            },
  { value: 'Space Grotesk',     label: 'Space Grotesk'     },
  { value: 'Inter',             label: 'Inter'             },
  { value: 'Plus Jakarta Sans', label: 'Plus Jakarta Sans' },
  { value: 'Sora',              label: 'Sora'              },
]

function ColorField({ label, desc, value, onChange }) {
  const inputRef = useRef(null)
  return (
    <div style={{ marginBottom: 18 }}>
      <label className="field-label">{label}</label>
      {desc && <p style={{ fontSize: '0.64rem', color: 'var(--text-muted)', marginBottom: 8, lineHeight: 1.45 }}>{desc}</p>}
      <div className="color-row">
        <div
          className="color-dot"
          style={{ background: value, boxShadow: `0 0 0 3px ${value}28` }}
          onClick={() => inputRef.current?.click()}
        />
        <input ref={inputRef} type="color" value={value} onChange={e => onChange(e.target.value)}
          style={{ position: 'absolute', opacity: 0, width: 0, height: 0, pointerEvents: 'none' }} />
        <input
          className="field-input"
          value={value}
          onChange={e => { if (/^#[0-9a-fA-F]{0,6}$/.test(e.target.value)) onChange(e.target.value) }}
          maxLength={7} spellCheck={false}
          style={{ fontFamily: 'monospace', letterSpacing: '0.05em' }}
        />
      </div>
    </div>
  )
}

export default function ThemePanel({ theme, onChange }) {
  return (
    <aside className="editor-sidebar">
      <div style={{ marginBottom: 20 }}>
        <div className="section-hdr" style={{ marginBottom: 4 }}>Theme & Style</div>
        <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: 1.55 }}>
          Colour and font changes apply live to all widget previews.
        </p>
      </div>

      {/* Colours */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: '16px 16px 6px', marginBottom: 14,
      }}>
        <div style={{ fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 7 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="13.5" cy="6.5" r=".5" /><circle cx="17.5" cy="10.5" r=".5" /><circle cx="8.5" cy="7.5" r=".5" /><circle cx="6.5" cy="12.5" r=".5" />
            <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z" />
          </svg>
          Colours
        </div>
        <ColorField label="Primary"    desc="Widget headers, clock, highlights"   value={theme.primary}    onChange={v => onChange({ primary: v })} />
        <ColorField label="Secondary"  desc="Timetable rows, success badges"       value={theme.secondary}  onChange={v => onChange({ secondary: v })} />
        <ColorField label="Background" desc="Mirror screen background"             value={theme.background} onChange={v => onChange({ background: v })} />
      </div>

      {/* Fonts */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: '16px', marginBottom: 14,
      }}>
        <div style={{ fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 7 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="4 7 4 4 20 4 20 7" /><line x1="9" y1="20" x2="15" y2="20" /><line x1="12" y1="4" x2="12" y2="20" />
          </svg>
          Font Family
        </div>
        {FONT_OPTIONS.map(opt => (
          <button
            key={opt.value}
            className={`font-btn${theme.fontFamily === opt.value ? ' active' : ''}`}
            onClick={() => onChange({ fontFamily: opt.value })}
          >
            <span style={{ fontFamily: opt.value, fontSize: '0.84rem', color: 'var(--text)' }}>{opt.label}</span>
            {theme.fontFamily === opt.value && (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
          </button>
        ))}
      </div>

      {/* Live preview */}
      <div style={{
        background: theme.background, border: '1px solid var(--border)',
        borderRadius: 16, padding: '16px',
      }}>
        <div style={{ fontSize: '0.62rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.35)', marginBottom: 12 }}>
          Mirror Preview
        </div>
        <div style={{ fontFamily: theme.fontFamily }}>
          <div style={{ fontSize: '2.4rem', fontWeight: 200, color: theme.primary, lineHeight: 1, letterSpacing: '-0.02em' }}>
            {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.45)', marginTop: 4, marginBottom: 12 }}>
            {new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.7rem',
            fontWeight: 600, color: theme.secondary,
            background: `${theme.secondary}15`, border: `1px solid ${theme.secondary}28`,
            borderRadius: 7, padding: '4px 10px',
          }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: theme.secondary }} />
            Period 2 — Science  Rm B4
          </div>
        </div>
      </div>
    </aside>
  )
}
