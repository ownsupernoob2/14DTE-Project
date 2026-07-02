import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import useBentoLayout from '../hooks/useBentoLayout.js'
import EditorNavbar from '../components/EditorNavbar.jsx'
import WidgetTray from '../components/WidgetTray.jsx'
import BentoGrid from '../components/BentoGrid.jsx'
import ThemePanel from '../components/ThemePanel.jsx'
import Toast from '../components/Toast.jsx'
import SettingsPanel from '../components/SettingsPanel.jsx'

export default function BentoEditor() {
  const {
    widgets, theme, status, loaded,
    fetchLayout, addWidget, moveWidget, resizeWidget,
    removeWidget, clearWidgets, updateWidgetData, updateTheme, saveLayout,
  } = useBentoLayout()

  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => { fetchLayout() }, [fetchLayout])

  const isSaving = status.type === 'saving'

  return (
    <motion.div
      className="editor-layout"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.28 }}
    >
      {/* ── Navbar ───────────────────────────────────── */}
      <EditorNavbar
        onSave={saveLayout}
        isSaving={isSaving}
        widgetCount={widgets.length}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {/* ── Left tray ────────────────────────────────── */}
      <WidgetTray onAdd={addWidget} onClear={clearWidgets} widgetCount={widgets.length} />

      {/* ── Centre canvas ────────────────────────────── */}
      <main className="editor-canvas" style={{ background: 'var(--bg)' }}>
        {/* Subtle dot grid overlay */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0,
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }} />

        {/* Radial accent glow behind the grid */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0,
          background: 'radial-gradient(ellipse 60% 50% at 50% 40%, rgba(79,142,247,0.055) 0%, transparent 70%)',
        }} />

        {!loaded ? (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1,
          }}>
            <motion.div
              animate={{ opacity: [0.35, 1, 0.35] }}
              transition={{ repeat: Infinity, duration: 1.4 }}
              style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}
            >
              Loading layout…
            </motion.div>
          </div>
        ) : (
          <div className="bento-grid-wrapper" style={{ position: 'relative', zIndex: 1 }}>
            <BentoGrid
              widgets={widgets}
              theme={theme}
              onMove={moveWidget}
              onResize={resizeWidget}
              onRemove={removeWidget}
              onUpdateData={updateWidgetData}
            />
          </div>
        )}
      </main>

      {/* ── Right theme sidebar ───────────────────────── */}
      <ThemePanel theme={theme} onChange={updateTheme} />

      {/* ── Settings slide-over ───────────────────────── */}
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* ── Toast ────────────────────────────────────── */}
      <Toast status={status} />
    </motion.div>
  )
}
