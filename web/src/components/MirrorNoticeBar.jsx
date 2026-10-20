/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { API_URL } from '../config'

// The admin's school-wide notice — the same one shown on every mirror.
export const NOTICE_LEVELS = {
  notice: { tag: 'NOTICE', bar: 'bg-[#0a1020] border-[#1e3a8a]', chip: 'bg-[#2563eb] text-white' },
  warning: { tag: 'WARNING', bar: 'bg-[#1a1205] border-[#78500f]', chip: 'bg-[#f59e0b] text-black' },
  urgent: { tag: 'URGENT', bar: 'bg-[#140a0a] border-[#3b1212]', chip: 'bg-[#ef4444] text-black' },
}

export function NoticeBarView({ message, level = 'notice' }) {
  const style = NOTICE_LEVELS[level] || NOTICE_LEVELS.notice
  return (
    <div className={`w-full border-b px-6 py-2 flex items-center gap-3 text-xs shrink-0 ${style.bar}`} role="status">
      <span className={`font-mono font-bold text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-none shrink-0 ${style.chip}`}>
        {style.tag}
      </span>
      <span className="font-sans font-medium text-white">{message}</span>
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
