import { useRef, useState, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  COLS, ROWS, CELL_SIZE, CELL_GAP, GRID_PAD,
  cellOrigin, cellSpanSize, snapToGrid, hasCollision, inBounds, GRID_TOTAL_W, GRID_TOTAL_H,
} from '../utils/gridUtils.js'
import PlacedWidget from './PlacedWidget.jsx'

function BentoCell({ col, row, highlight }) {
  return (
    <div
      className={`bento-cell${highlight ? ' highlight' : ''}`}
      style={{ gridColumn: col + 1, gridRow: row + 1 }}
    />
  )
}

export default function BentoGrid({ widgets, theme, onMove, onResize, onRemove, onUpdateData }) {
  const gridRef = useRef(null)
  const [ghost, setGhost] = useState(null)
  // ghost: { x, y, w, h, valid, col, row, id, spanW?, spanH?, isResize }

  /* ── Drag callbacks (from PlacedWidget native pointer) ── */
  const handleDragMove = useCallback((e, widgetId) => {
    if (!gridRef.current) return
    const rect   = gridRef.current.getBoundingClientRect()
    const px     = e.clientX - rect.left
    const py     = e.clientY - rect.top
    const target = widgets.find(w => w.id === widgetId)
    if (!target) return

    const { col, row } = snapToGrid(px, py, target.grid_width, target.grid_height)
    const origin = cellOrigin(col, row)
    const size   = cellSpanSize(target.grid_width, target.grid_height)
    const valid  = inBounds(col, row, target.grid_width, target.grid_height) &&
                   !hasCollision(col, row, target.grid_width, target.grid_height, widgets, widgetId)

    setGhost({ x: origin.x, y: origin.y, w: size.width, h: size.height, col, row, valid, id: widgetId })
  }, [widgets])

  const handleDragEnd = useCallback((widgetId) => {
    if (ghost?.id === widgetId && ghost?.valid) {
      onMove(widgetId, ghost.col, ghost.row)
    }
    setGhost(null)
  }, [ghost, onMove])

  /* ── Resize callbacks ───────────────────────────────── */
  const handleResizeDrag = useCallback((e, widgetId) => {
    if (!gridRef.current) return
    const target = widgets.find(w => w.id === widgetId)
    if (!target) return
    const rect   = gridRef.current.getBoundingClientRect()
    const origin = cellOrigin(target.grid_x, target.grid_y)
    const relX   = e.clientX - rect.left - origin.x
    const relY   = e.clientY - rect.top  - origin.y

    const rawW = Math.max(1, Math.round((relX + CELL_SIZE * 0.5) / (CELL_SIZE + CELL_GAP)))
    const rawH = Math.max(1, Math.round((relY + CELL_SIZE * 0.5) / (CELL_SIZE + CELL_GAP)))
    const spanW = Math.max(1, Math.min(rawW, COLS - target.grid_x))
    const spanH = Math.max(1, Math.min(rawH, ROWS - target.grid_y))
    const size  = cellSpanSize(spanW, spanH)
    const valid = !hasCollision(target.grid_x, target.grid_y, spanW, spanH, widgets, widgetId) &&
                  inBounds(target.grid_x, target.grid_y, spanW, spanH)

    setGhost({
      x: origin.x, y: origin.y, w: size.width, h: size.height,
      col: target.grid_x, row: target.grid_y,
      spanW, spanH, valid, id: widgetId, isResize: true,
    })
  }, [widgets])

  const handleResizeEnd = useCallback((widgetId) => {
    if (ghost?.id === widgetId && ghost?.isResize && ghost?.valid) {
      onResize(widgetId, ghost.spanW, ghost.spanH)
    }
    setGhost(null)
  }, [ghost, onResize])

  /* ── Highlight which cells the ghost covers ─────────── */
  const ghostCells = new Set()
  if (ghost) {
    const { col, row } = ghost
    const spanW = ghost.spanW || (widgets.find(w => w.id === ghost.id)?.grid_width || 1)
    const spanH = ghost.spanH || (widgets.find(w => w.id === ghost.id)?.grid_height || 1)
    for (let c = col; c < col + spanW; c++)
      for (let r = row; r < row + spanH; r++)
        ghostCells.add(`${c},${r}`)
  }

  return (
    <div
      ref={gridRef}
      style={{ position: 'relative', width: GRID_TOTAL_W, height: GRID_TOTAL_H, flexShrink: 0 }}
    >
      {/* Background cell grid */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        display: 'grid',
        gridTemplateColumns: `repeat(${COLS}, ${CELL_SIZE}px)`,
        gridTemplateRows:    `repeat(${ROWS}, ${CELL_SIZE}px)`,
        gap: CELL_GAP, padding: GRID_PAD,
      }}>
        {Array.from({ length: ROWS }).map((_, r) =>
          Array.from({ length: COLS }).map((_, c) => (
            <BentoCell
              key={`${c}-${r}`}
              col={c} row={r}
              highlight={ghost?.valid && ghostCells.has(`${c},${r}`)}
            />
          ))
        )}
      </div>

      {/* Drop / resize ghost */}
      <AnimatePresence>
        {ghost && (
          <motion.div
            className={`drop-ghost${ghost.valid ? '' : ' invalid'}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.08 }}
            style={{ left: ghost.x, top: ghost.y, width: ghost.w, height: ghost.h }}
          />
        )}
      </AnimatePresence>

      {/* Placed widgets */}
      <AnimatePresence>
        {widgets.map(w => (
          <PlacedWidget
            key={w.id}
            widget={w}
            theme={theme}
            onDragMove={handleDragMove}
            onDragEnd={handleDragEnd}
            onResizeDrag={handleResizeDrag}
            onResizeEnd={handleResizeEnd}
            onRemove={onRemove}
            onUpdateData={onUpdateData}
            gridRef={gridRef}
          />
        ))}
      </AnimatePresence>

      {/* Empty state */}
      {widgets.length === 0 && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none', gap: 14,
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: 20,
            border: '1.5px dashed rgba(255,255,255,0.08)',
            background: 'rgba(255,255,255,0.02)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5">
              <rect x="3" y="3" width="7" height="7" rx="2" />
              <rect x="14" y="3" width="7" height="7" rx="2" />
              <rect x="3" y="14" width="7" height="7" rx="2" />
              <rect x="14" y="14" width="7" height="7" rx="2" />
            </svg>
          </div>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-dim)', textAlign: 'center', maxWidth: 220 }}>
            Select a widget from the tray to start building
          </p>
        </div>
      )}
    </div>
  )
}
