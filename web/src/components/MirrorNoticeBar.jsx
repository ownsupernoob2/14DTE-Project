/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { API_URL } from '../config'

// The admin's school-wide notice — the same one shown on every mirror.
export const NOTICE_LEVELS = {
  notice: { tag: 'NOTICE', accent: 'border-l-[#3b82f6]', text: 'text-[#3b82f6]' },
  warning: { tag: 'WARNING', accent: 'border-l-[#f59e0b]', text: 'text-[#f59e0b]' },
  urgent: { tag: 'URGENT', accent: 'border-l-[#ef4444]', text: 'text-[#ef4444]' },
}

// Flat panel with an accent stripe, like the notice cards: no outline.
export function NoticeBarView({ message, level = 'notice' }) {
  const style = NOTICE_LEVELS[level] || NOTICE_LEVELS.notice
  return (
    <div
      className={`w-full bg-[#111111] border-l-8 ${style.accent} px-6 py-4 flex flex-col gap-1 shrink-0`}
      role="status"
    >
      <span className={`font-mono font-extrabold text-sm uppercase tracking-[0.15em] ${style.text}`}>
        {style.tag}
      </span>
      <span className="font-sans font-bold text-white text-xl sm:text-2xl leading-snug">{message}</span>
    </div>
  )
}

export default function MirrorNoticeBar() {
  const [banner, setBanner] = useState({ message: '', level: 'notice' })

  useEffect(() => {
    let cancelled = false
    const load = () =>
      fetch(`${API_URL}/api/banner`)
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => { if (data && !cancelled) setBanner({ message: data.message || '', level: data.level || 'notice' }) })
        .catch(() => {})
    load()
    const interval = setInterval(load, 30000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <AnimatePresence mode="wait">
      {banner.message && (
        <motion.div
          key={banner.message + banner.level}
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
        >
          <NoticeBarView message={banner.message} level={banner.level} />
        </motion.div>
      )}
    </AnimatePresence>
  )
}
