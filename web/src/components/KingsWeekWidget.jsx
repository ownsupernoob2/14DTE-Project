import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { API_URL } from '../config'

// King's Week, laid out like the mirror: the latest story spans the full
// width, the rest pair up below it; selecting one opens it in full.

const REFRESH_MS = 15 * 60 * 1000

function meta(article) {
  return [article.author, article.date].filter(Boolean).join(' • ')
}

function summaryWords(text, max = 16) {
  const words = (text || '').trim().split(/\s+/)
  return words.length > max ? `${words.slice(0, max).join(' ')}...` : text
}

function ArticleCard({ article, feature, onOpen }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(article)}
      className={`group relative w-full overflow-hidden rounded-[14px] bg-[#0c0c12] text-left cursor-pointer
        outline-none ring-0 transition-shadow hover:shadow-[0_0_0_3px_#ffffff] focus-visible:shadow-[0_0_0_3px_#ffffff]
        ${feature ? 'min-h-[260px] col-span-2' : 'min-h-[132px]'}`}
    >
      {article.imageUrl && (
        <img
          src={article.imageUrl}
          alt=""
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover opacity-[0.78] group-hover:opacity-100 transition-opacity"
        />
      )}
      {/* Dark at the bottom where the text sits, clear at the top. */}
      <div
        className="absolute inset-0"
        style={{ background: 'linear-gradient(to bottom, rgba(6,6,12,0.16) 18%, rgba(5,5,11,0.69) 64%, rgba(3,3,8,0.94) 100%)' }}
      />
      <div className={`relative h-full flex flex-col justify-end ${feature ? 'p-4 gap-2.5 min-h-[260px]' : 'p-2.5 gap-2 min-h-[132px]'}`}>
        {meta(article) && (
          <span className={`font-extrabold tracking-wider text-white ${feature ? 'text-sm' : 'text-[11px]'}`}>
            {meta(article)}
          </span>
        )}
        <span className={`font-bold text-white leading-tight ${feature ? 'text-2xl' : 'text-base'}`}>
          {article.title}
        </span>
        {feature && article.summary && (
          <span className="text-sm text-[#f1f5f9] leading-snug">{summaryWords(article.summary)}</span>
        )}
      </div>
    </button>
  )
}

function ArticleModal({ article, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const paragraphs = (article.body || article.summary || '').split(/\n{2,}/).filter(Boolean)
  const hero = article.largeImageUrl || article.imageUrl

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] bg-black/80 flex items-center justify-center p-4 sm:p-8"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={article.title}
    >
      <motion.article
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.96, opacity: 0 }}
        transition={{ duration: 0.25 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl max-h-full overflow-y-auto bg-[#0b0b10] rounded-[12px] p-5 sm:p-6 flex flex-col gap-4"
      >
        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="text-[11px] font-extrabold tracking-[0.15em] uppercase text-[#cbd5e1] hover:text-white cursor-pointer"
          >
            Close
          </button>
        </div>
        {hero && <img src={hero} alt="" className="w-full rounded-[8px]" />}
        <h2 className="text-2xl sm:text-[28px] font-extrabold text-white leading-tight">{article.title}</h2>
        {meta(article) && <p className="text-sm font-semibold tracking-wider text-[#cbd5e1]">{meta(article)}</p>}
        <div className="flex flex-col gap-3">
          {paragraphs.map((p, i) => (
            <p key={i} className="text-[15px] leading-relaxed text-white whitespace-pre-line">{p}</p>
          ))}
        </div>
        {article.link && (
          <a
            href={article.link}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold text-[#94a3b8] hover:text-white underline"
          >
            Read the full story
          </a>
        )}
      </motion.article>
    </motion.div>
  )
}

export default function KingsWeekWidget() {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      fetch(`${API_URL}/api/kings-week`)
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.status))))
        .then((json) => { if (!cancelled) { setData(json); setFailed(false) } })
        .catch(() => { if (!cancelled) setFailed(true) })
    load()
    const interval = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const articles = (data?.articles || []).filter((a) => a.title)
  const label = [data?.edition || data?.title, data?.date].filter(Boolean).join('  •  ')

  return (
    <section className="flex flex-col shrink-0" aria-label="King's Week">
      <div className="flex items-center justify-between mb-3 shrink-0">
        <span className="text-sm font-bold text-[#cbd5e1]">{label || "King's Week"}</span>
      </div>

      {!data && !failed && (
        <div className="grid grid-cols-2 gap-3" aria-hidden="true">
          <div className="col-span-2 h-[260px] rounded-[14px] bg-[#0c0c12] animate-pulse" />
          <div className="h-[132px] rounded-[14px] bg-[#0c0c12] animate-pulse" />
          <div className="h-[132px] rounded-[14px] bg-[#0c0c12] animate-pulse" />
        </div>
      )}

      {(failed || (data && articles.length === 0)) && (
        <p className="text-sm font-bold text-[#cbd5e1]">King&apos;s Week is not available right now.</p>
      )}

      {articles.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {articles.map((a, i) => (
            <ArticleCard key={a.id || a.link || i} article={a} feature={i === 0} onOpen={setOpen} />
          ))}
        </div>
      )}

      <AnimatePresence>
        {open && <ArticleModal article={open} onClose={() => setOpen(null)} />}
      </AnimatePresence>
    </section>
  )
}
