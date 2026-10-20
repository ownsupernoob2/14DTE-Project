import { motion, AnimatePresence } from 'framer-motion'
import { useMe } from '../contexts/MeContext'

// Messages from an administrator, e.g. "Your face scan was removed…". Shown
// until the student acknowledges them.
export default function AccountMessages() {
  const { messages, dismissMessages, contactEmail } = useMe()

  return (
    <AnimatePresence>
      {messages.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="account-messages-title"
        >
          <motion.div
            initial={{ scale: 0.97, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            className="max-w-md w-full bg-[#0a0a0a] border border-[#333333] rounded-none p-7 font-mono"
          >
            <div className="flex items-center gap-3 mb-4">
              <span className="material-symbols-outlined text-white text-2xl">info</span>
              <h2 id="account-messages-title" className="text-sm font-bold text-white uppercase tracking-wider">
                Changes to your account
              </h2>
            </div>
            <ul className="flex flex-col gap-3 mb-6">
              {messages.map((m) => (
                <li key={m.id} className="bg-[#121212] border border-[#222222] p-3 text-xs text-[#d0d0d0] leading-relaxed">
                  {m.message}
                  <div className="mt-2 text-[10px] text-[#666666] uppercase tracking-wider">
                    {new Date(m.created_at * 1000).toLocaleString()}
                  </div>
                </li>
              ))}
            </ul>
            <p className="text-[11px] text-[#888888] mb-5 leading-relaxed">
              Questions? Email{' '}
              <a href={`mailto:${contactEmail}`} className="text-white underline">{contactEmail}</a>.
            </p>
            <button
              onClick={dismissMessages}
              className="w-full py-3 bg-white text-black hover:bg-[#e0e0e0] text-xs font-bold uppercase tracking-wider rounded-none cursor-pointer"
            >
              OK, got it
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
