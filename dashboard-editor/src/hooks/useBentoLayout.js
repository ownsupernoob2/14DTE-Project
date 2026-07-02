import { useState, useCallback } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import {
  findFreeSlot, hasCollision, inBounds, serializeToSchema,
  COLS, ROWS,
} from '../utils/gridUtils.js'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

// Default grid spans per widget type
const DEFAULT_SPANS = {
  clock:     { w: 2, h: 1 },
  notices:   { w: 3, h: 3 },
  timetable: { w: 3, h: 2 },
  note:      { w: 2, h: 2 },
  weather:   { w: 1, h: 2 },
}

const DEFAULT_THEME = {
  primary:    '#4f8ef7',
  secondary:  '#22c9a0',
  background: '#0b0d14',
  fontFamily: 'Outfit',
}

export default function useBentoLayout() {
  const { getAccessTokenSilently } = useAuth0()

  const [widgets, setWidgets] = useState([])
  const [theme,   setTheme]   = useState(DEFAULT_THEME)
  const [status,  setStatus]  = useState({ type: null, msg: '' })
  const [loaded,  setLoaded]  = useState(false)

  /* ── Fetch ─────────────────────────────────────────────── */
  const fetchLayout = useCallback(async () => {
    try {
      const token = await getAccessTokenSilently()
      const res   = await fetch(`${API_URL}/api/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('fetch failed')
      const data   = await res.json()
      const config = data.config || {}

      const colors = config.theme?.colors || {}
      const fonts  = config.theme?.fonts  || {}
      setTheme({
        primary:    colors.primary    || DEFAULT_THEME.primary,
        secondary:  colors.secondary  || DEFAULT_THEME.secondary,
        background: colors.background || DEFAULT_THEME.background,
        fontFamily: fonts.family      || DEFAULT_THEME.fontFamily,
      })

      const slots = config.slots || []
      const restored = slots.map(slot => {
        const w = slot.widget || {}
        return {
          id:          w.id          || `w-${Math.random().toString(36).slice(2)}`,
          type:        w.type        || 'note',
          grid_x:      Number(w.grid_x)      ?? 0,
          grid_y:      Number(w.grid_y)      ?? 0,
          grid_width:  Number(w.grid_width)  || 1,
          grid_height: Number(w.grid_height) || 1,
          data:        w.data || {},
        }
      }).filter(w => inBounds(w.grid_x, w.grid_y, w.grid_width, w.grid_height))

      setWidgets(restored)
    } catch (e) {
      console.warn('[BentoLayout] fetch:', e.message)
    } finally {
      setLoaded(true)
    }
  }, [getAccessTokenSilently])

  /* ── Add widget ────────────────────────────────────────── */
  const addWidget = useCallback((type, col = null, row = null) => {
    const spans = DEFAULT_SPANS[type] || { w: 1, h: 1 }
    let targetCol = col
    let targetRow = row

    if (targetCol === null || targetRow === null) {
      const slot = findFreeSlot(spans.w, spans.h, widgets)
      if (!slot) return false
      targetCol = slot.col
      targetRow = slot.row
    } else {
      targetCol = Math.max(0, Math.min(targetCol, COLS - spans.w))
      targetRow = Math.max(0, Math.min(targetRow, ROWS - spans.h))
      if (hasCollision(targetCol, targetRow, spans.w, spans.h, widgets)) {
        const slot = findFreeSlot(spans.w, spans.h, widgets)
        if (!slot) return false
        targetCol = slot.col
        targetRow = slot.row
      }
    }

    setWidgets(prev => [...prev, {
      id:          `w-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`,
      type,
      grid_x:      targetCol,
      grid_y:      targetRow,
      grid_width:  spans.w,
      grid_height: spans.h,
      data:        {},
    }])
    return true
  }, [widgets])

  /* ── Move widget ───────────────────────────────────────── */
  const moveWidget = useCallback((id, newCol, newRow) => {
    setWidgets(prev => {
      const target = prev.find(w => w.id === id)
      if (!target) return prev
      const col = Math.max(0, Math.min(newCol, COLS - target.grid_width))
      const row = Math.max(0, Math.min(newRow, ROWS - target.grid_height))
      if (hasCollision(col, row, target.grid_width, target.grid_height, prev, id)) return prev
      return prev.map(w => w.id === id ? { ...w, grid_x: col, grid_y: row } : w)
    })
  }, [])

  /* ── Resize widget ─────────────────────────────────────── */
  const resizeWidget = useCallback((id, newW, newH) => {
    setWidgets(prev => {
      const target = prev.find(w => w.id === id)
      if (!target) return prev
      const spanW = Math.max(1, Math.min(newW, COLS - target.grid_x))
      const spanH = Math.max(1, Math.min(newH, ROWS - target.grid_y))
      if (hasCollision(target.grid_x, target.grid_y, spanW, spanH, prev, id)) return prev
      return prev.map(w => w.id === id ? { ...w, grid_width: spanW, grid_height: spanH } : w)
    })
  }, [])

  /* ── Remove / clear ────────────────────────────────────── */
  const removeWidget  = useCallback((id) => setWidgets(prev => prev.filter(w => w.id !== id)), [])
  const clearWidgets  = useCallback(() => setWidgets([]), [])

  /* ── Update data (for widget-internal state) ───────────── */
  const updateWidgetData = useCallback((id, data) => {
    setWidgets(prev => prev.map(w => w.id === id ? { ...w, data: { ...w.data, ...data } } : w))
  }, [])

  /* ── Theme ─────────────────────────────────────────────── */
  const updateTheme = useCallback((patch) => setTheme(prev => ({ ...prev, ...patch })), [])

  /* ── Save ──────────────────────────────────────────────── */
  const saveLayout = useCallback(async () => {
    setStatus({ type: 'saving', msg: 'Saving layout…' })
    try {
      const token   = await getAccessTokenSilently()
      const payload = serializeToSchema(widgets, theme)
      const res = await fetch(`${API_URL}/api/dashboard/widgets/bulk`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setStatus({ type: 'saved', msg: 'Layout saved' })
      setTimeout(() => setStatus({ type: null, msg: '' }), 2500)
    } catch (e) {
      setStatus({ type: 'error', msg: 'Save failed — check connection' })
      setTimeout(() => setStatus({ type: null, msg: '' }), 3000)
    }
  }, [widgets, theme, getAccessTokenSilently])

  return {
    widgets, theme, status, loaded,
    fetchLayout, addWidget, moveWidget, resizeWidget,
    removeWidget, clearWidgets, updateWidgetData,
    updateTheme, saveLayout,
  }
}
