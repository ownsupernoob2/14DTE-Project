/**
 * gridUtils.js — 6×6 bento grid math helpers.
 */

export const COLS = 6
export const ROWS = 6
export const CELL_SIZE = 180   // px
export const CELL_GAP  = 10    // px
export const GRID_PAD  = 40    // px

/** Pixel origin of cell (col, row) relative to grid container */
export function cellOrigin(col, row) {
  return {
    x: GRID_PAD + col * (CELL_SIZE + CELL_GAP),
    y: GRID_PAD + row * (CELL_SIZE + CELL_GAP),
  }
}

/** Pixel size for a widget spanning (w cols, h rows) */
export function cellSpanSize(w, h) {
  return {
    width:  w * CELL_SIZE + (w - 1) * CELL_GAP,
    height: h * CELL_SIZE + (h - 1) * CELL_GAP,
  }
}

export const GRID_TOTAL_W = GRID_PAD * 2 + COLS * (CELL_SIZE + CELL_GAP) - CELL_GAP
export const GRID_TOTAL_H = GRID_PAD * 2 + ROWS * (CELL_SIZE + CELL_GAP) - CELL_GAP

/**
 * Snap raw pixel coordinates to the nearest valid grid cell (col, row),
 * clamped so the widget stays fully inside the grid.
 */
export function snapToGrid(px, py, spanW = 1, spanH = 1) {
  const rawCol = Math.round((px - GRID_PAD) / (CELL_SIZE + CELL_GAP))
  const rawRow = Math.round((py - GRID_PAD) / (CELL_SIZE + CELL_GAP))
  const col = Math.max(0, Math.min(rawCol, COLS - spanW))
  const row = Math.max(0, Math.min(rawRow, ROWS - spanH))
  return { col, row }
}

/**
 * Derive orientation hint from widget span dimensions.
 */
export function orientationFor(spanW, spanH) {
  if (spanW >= 2 && spanH === 1) return 'horizontal'
  if (spanW === 1 && spanH >= 2) return 'vertical'
  return 'square'
}

/**
 * Derive a CSS size class for font scaling based on total cell area.
 */
export function sizeClass(spanW, spanH) {
  const area = spanW * spanH
  if (area <= 1) return 'widget-size-xs'
  if (area <= 2) return 'widget-size-sm'
  if (area <= 4) return 'widget-size-md'
  if (area <= 6) return 'widget-size-lg'
  return 'widget-size-xl'
}

/** AABB collision check in grid-cell space, excluding self by id */
export function hasCollision(col, row, spanW, spanH, widgets, excludeId = null) {
  for (const w of widgets) {
    if (w.id === excludeId) continue
    const overlap =
      col        < w.grid_x + w.grid_width  &&
      col + spanW > w.grid_x                &&
      row        < w.grid_y + w.grid_height &&
      row + spanH > w.grid_y
    if (overlap) return true
  }
  return false
}

/** Check all cells covered are within grid bounds */
export function inBounds(col, row, spanW, spanH) {
  return col >= 0 && row >= 0 && col + spanW <= COLS && row + spanH <= ROWS
}

/** Find first free top-left cell that fits (spanW, spanH) */
export function findFreeSlot(spanW, spanH, widgets) {
  for (let r = 0; r <= ROWS - spanH; r++) {
    for (let c = 0; c <= COLS - spanW; c++) {
      if (!hasCollision(c, r, spanW, spanH, widgets)) return { col: c, row: r }
    }
  }
  return null
}

/** Serialize widgets + theme to the Go backend JSON schema */
export function serializeToSchema(widgets, theme) {
  return {
    theme: {
      colors: {
        primary:    theme.primary,
        secondary:  theme.secondary,
        background: theme.background,
      },
      fonts: {
        family:        theme.fontFamily,
        size_modifier: 1.0,
      },
    },
    slots: widgets.map(w => ({
      slot_id:     `slot_${w.id}`,
      orientation: orientationFor(w.grid_width, w.grid_height),
      widget: {
        id:          w.id,
        type:        w.type,
        grid_x:      w.grid_x,
        grid_y:      w.grid_y,
        grid_width:  w.grid_width,
        grid_height: w.grid_height,
        data:        w.data || {},
      },
    })),
  }
}
