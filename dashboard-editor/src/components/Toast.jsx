import { AnimatePresence, motion } from 'framer-motion'

const ICONS = {
  saving: (
    <motion.span
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 0.7, ease: 'linear' }}
      style={{ display: 'inline-block', fontSize: '0.9rem' }}
    >
      ⟳
    </motion.span>
  ),
  saved:  <span style={{ color: '#10b981' }}>✓</span>,
  error:  <span style={{ color: '#f87171' }}>✕</span>,
}

export default function Toast({ status }) {
  const visible = !!status?.type

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="toast"
          initial={{ opacity: 0, y: 16, scale: 0.95 }}
          animate={{ opacity: 1, y: 0,  scale: 1    }}
          exit={{    opacity: 0, y: 16, scale: 0.95 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          style={{
            borderColor: status.type === 'error'
              ? 'rgba(239,68,68,0.3)'
              : status.type === 'saved'
              ? 'rgba(16,185,129,0.3)'
              : 'var(--border)',
          }}
        >
          {ICONS[status.type]}
          <span>{status.msg}</span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
