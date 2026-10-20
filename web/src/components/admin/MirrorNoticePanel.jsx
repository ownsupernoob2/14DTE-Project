import { useEffect, useState } from 'react'
import { useMe } from '../../contexts/MeContext'
import { API_URL } from '../../config'
import { NoticeBarView } from '../MirrorNoticeBar'

const MAX_LEN = 280
const LEVELS = [
  { id: 'notice', label: 'Notice', sub: 'General information', icon: 'info' },
  { id: 'warning', label: 'Warning', sub: 'Needs attention', icon: 'warning' },
  { id: 'urgent', label: 'Urgent', sub: 'Act now', icon: 'emergency_home' },
]

function minutesUntilMidnight() {
  const end = new Date()
  end.setHours(24, 0, 0, 0)
  return Math.max(1, Math.round((end - new Date()) / 60000))
}

const EXPIRY = [
  { id: 'none', label: 'Until I clear it', minutes: () => 0 },
  { id: '1h', label: '1 hour', minutes: () => 60 },
  { id: '3h', label: '3 hours', minutes: () => 180 },
  { id: 'today', label: 'End of today', minutes: minutesUntilMidnight },
  { id: '24h', label: '24 hours', minutes: () => 1440 },
  { id: '3d', label: '3 days', minutes: () => 4320 },
  { id: '7d', label: '1 week', minutes: () => 10080 },
]

export default function MirrorNoticePanel() {
  const { authFetch } = useMe()
  const [current, setCurrent] = useState(null)
  const [message, setMessage] = useState('')
  const [level, setLevel] = useState('notice')
  const [expiry, setExpiry] = useState('none')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')

  useEffect(() => {
    let cancelled = false
    fetch(`${API_URL}/api/banner`)
      .then((res) => res.json())
      .then((b) => {
        if (cancelled) return
        setCurrent(b)
        if (b.message) {
          setMessage(b.message)
          setLevel(b.level || 'notice')
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const show = (msg) => {
    setFeedback(msg)
    setTimeout(() => setFeedback(''), 6000)
  }

  const publish = async (text) => {
    setBusy(true)
    try {
      const res = await authFetch('/api/admin/banner', {
        method: 'POST',
        body: JSON.stringify({
          message: text,
          level,
          expires_in_minutes: EXPIRY.find((e) => e.id === expiry).minutes(),
        }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
      setCurrent(body)
      if (!text) setMessage('')
      show(text ? 'Published. Mirrors show it within 15 seconds.' : 'Cleared from every mirror.')
    } catch (e) {
      show(`Error: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  const trimmed = message.trim()

  return (
    <section className="flex flex-col gap-6">
      <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6 flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-white text-lg">campaign</span>
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Mirror Notice</h3>
            <p className="text-xs text-[#888888] mt-0.5 uppercase tracking-wider">
              One message across the top of every mirror, for guests and signed-in students, and on the website
            </p>
          </div>
        </div>

        <label className="flex flex-col gap-2">
          <span className="text-[11px] text-[#888888] uppercase tracking-wider font-bold">Message</span>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value.replace(/\s*\n\s*/g, ' '))}
            maxLength={MAX_LEN}
            rows={3}
            placeholder="e.g. Assembly moved to the gym at 11:00 today"
            className="bg-[#121212] border border-[#333333] focus:border-white outline-none p-3 text-sm text-white font-sans resize-none rounded-none"
          />
          <span className={`text-[10px] text-right font-mono ${message.length > MAX_LEN - 20 ? 'text-[#f59e0b]' : 'text-[#555555]'}`}>
            {message.length}/{MAX_LEN}
          </span>
        </label>

        <div className="flex flex-col gap-2">
          <span className="text-[11px] text-[#888888] uppercase tracking-wider font-bold">Level</span>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {LEVELS.map((l) => {
              const active = level === l.id
              return (
                <button
                  key={l.id}
                  onClick={() => setLevel(l.id)}
                  className={`p-3 text-left rounded-none border cursor-pointer transition-all ${
                    active ? 'bg-white text-black border-white' : 'bg-[#121212] hover:bg-[#1a1a1a] text-white border-[#262626]'
                  }`}
                >
                  <span className="material-symbols-outlined text-base">{l.icon}</span>
                  <div className="text-[11px] font-bold tracking-wider uppercase mt-1">{l.label}</div>
                  <div className={`text-[10px] mt-0.5 ${active ? 'text-[#333333]' : 'text-[#777777]'}`}>{l.sub}</div>
                </button>
              )
            })}
          </div>
        </div>

        <label className="flex flex-col gap-2 max-w-xs">
          <span className="text-[11px] text-[#888888] uppercase tracking-wider font-bold">Show for</span>
          <select
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            className="bg-[#121212] border border-[#333333] p-2 text-xs text-white font-mono rounded-none"
          >
            {EXPIRY.map((e) => <option key={e.id} value={e.id}>{e.label}</option>)}
          </select>
        </label>

        <div className="flex flex-col gap-2">
          <span className="text-[11px] text-[#888888] uppercase tracking-wider font-bold">Preview</span>
          <div className="border border-[#222222] bg-black min-h-[38px]">
            {trimmed
              ? <NoticeBarView message={trimmed} level={level} />
              : <p className="text-xs text-[#555555] font-mono p-3">Type a message to preview it.</p>}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => publish(trimmed)}
            disabled={busy || !trimmed}
            className="inline-flex items-center gap-2 px-5 py-2 text-xs font-bold uppercase bg-white text-black hover:bg-[#e0e0e0] cursor-pointer disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-base">send</span>
            Publish to mirrors
          </button>
          {current?.message && (
            <button
              onClick={() => publish('')}
              disabled={busy}
              className="px-5 py-2 text-xs font-bold uppercase border border-[#333333] text-white hover:border-white cursor-pointer disabled:opacity-50"
            >
              Clear notice
            </button>
          )}
          {feedback && (
            <span className={`text-xs font-mono flex items-center gap-1.5 ${feedback.startsWith('Error') ? 'text-red-400' : 'text-[#22c55e]'}`}>
              <span className="material-symbols-outlined text-sm">{feedback.startsWith('Error') ? 'error' : 'check_circle'}</span>
              {feedback}
            </span>
          )}
        </div>
      </div>

      <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
        <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3">Showing now</h3>
        {current?.message ? (
          <div className="flex flex-col gap-3">
            <NoticeBarView message={current.message} level={current.level} />
            <p className="text-[11px] text-[#888888] font-mono">
              Posted {current.updated_at ? new Date(current.updated_at * 1000).toLocaleString() : ''}
              {current.updated_by ? ` by ${current.updated_by}` : ''}
              {' · '}
              {current.expires_at ? `until ${new Date(current.expires_at * 1000).toLocaleString()}` : 'until cleared'}
            </p>
          </div>
        ) : (
          <p className="text-xs text-[#666666] font-mono">No notice is showing on the mirrors.</p>
        )}
      </div>
    </section>
  )
}
