import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useMe } from '../../contexts/MeContext'

const fmtDate = (unix) => (unix ? new Date(unix * 1000).toLocaleDateString() : '—')
const fmtDateTime = (unix) => (unix ? new Date(unix * 1000).toLocaleString() : '—')

const ACTIONS = {
  face: { label: 'Remove face scan', what: 'face scan' },
  barcode: { label: 'Remove student ID', what: 'student ID' },
  timetable: { label: 'Remove timetable link', what: 'timetable link' },
  delete: { label: 'Delete user', what: 'account and all of its data' },
}

function Check({ on, title }) {
  return on ? (
    <span className="inline-flex items-center gap-1 text-white" title={title}>
      <span className="material-symbols-outlined text-sm">check</span>
      {title && <span className="text-[10px] text-[#888888]">{title}</span>}
    </span>
  ) : (
    <span className="text-[#444444]">—</span>
  )
}

function StatCard({ label, value, icon }) {
  return (
    <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5">
      <div className="flex items-center justify-between text-[#888888] mb-3">
        <span className="text-[11px] uppercase tracking-wider font-bold">{label}</span>
        <span className="material-symbols-outlined text-lg text-white">{icon}</span>
      </div>
      <span className="text-3xl font-extrabold text-white font-mono">{value}</span>
    </div>
  )
}

export default function UsersPanel() {
  const { authFetch, me, contactEmail } = useMe()
  const [query, setQuery] = useState('')
  const [data, setData] = useState({ users: [], totals: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [pending, setPending] = useState(null) // { user, action }
  const [working, setWorking] = useState(false)

  const load = useCallback(async (q) => {
    setLoading(true)
    setError('')
    try {
      const res = await authFetch(`/api/admin/users?q=${encodeURIComponent(q)}`)
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `HTTP ${res.status}`)
      setData(await res.json())
    } catch (e) {
      setError(e.message || 'Could not load users')
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    const t = setTimeout(() => load(query), 250)
    return () => clearTimeout(t)
  }, [query, load])

  const runAction = async () => {
    if (!pending) return
    const { user, action } = pending
    setWorking(true)
    try {
      const id = encodeURIComponent(user.id)
      const path = action === 'delete' ? `/api/admin/users/${id}` : `/api/admin/users/${id}/${action}`
      const res = await authFetch(path, { method: 'DELETE' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
      setFeedback(body.message || 'Done')
      setTimeout(() => setFeedback(''), 6000)
      setPending(null)
      load(query)
    } catch (e) {
      setFeedback(`Error: ${e.message}`)
    } finally {
      setWorking(false)
    }
  }

  const totals = data.totals || {}

  return (
    <section className="flex flex-col gap-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Users signed up" value={totals.users ?? 0} icon="group" />
        <StatCard label="Face scans" value={totals.with_face ?? 0} icon="face" />
        <StatCard label="Student IDs linked" value={totals.with_barcode ?? 0} icon="badge" />
      </div>

      <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-5">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span className="material-symbols-outlined text-white text-lg">manage_accounts</span>
              Registered Users
            </h3>
            <p className="text-xs text-[#888888] mt-0.5 uppercase tracking-wider">
              Removing data tells the student next time they sign in, with {contactEmail} to contact
            </p>
          </div>
          <label className="flex items-center gap-2 bg-[#121212] border border-[#333333] px-3 py-2 w-full md:w-80">
            <span className="material-symbols-outlined text-base text-[#888888]">search</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name, email or student ID"
              aria-label="Search users"
              className="bg-transparent outline-none text-xs text-white placeholder-[#555555] w-full font-mono"
            />
          </label>
        </div>

        {feedback && (
          <div className={`mb-4 text-xs font-mono flex items-center gap-1.5 ${feedback.startsWith('Error') ? 'text-red-400' : 'text-[#22c55e]'}`}>
            <span className="material-symbols-outlined text-sm">{feedback.startsWith('Error') ? 'error' : 'check_circle'}</span>
            {feedback}
          </div>
        )}
        {error && <p className="text-xs text-red-400 font-mono mb-4">{error}</p>}

        {loading && data.users.length === 0 ? (
          <div className="py-12 text-center text-[#666666] text-xs uppercase tracking-widest">Loading users…</div>
        ) : data.users.length === 0 ? (
          <div className="py-12 text-center text-[#666666] font-mono text-xs border border-dashed border-[#222222] bg-[#0a0a0a]">
            {query ? 'No users match that search.' : 'No one has signed up yet.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-[#080808] border-b border-[#222222] text-[#888888] font-mono uppercase text-[10px] tracking-wider">
                  <th className="py-3 px-3">User</th>
                  <th className="py-3 px-3">Signed up with</th>
                  <th className="py-3 px-3">Student ID</th>
                  <th className="py-3 px-3">Face scan</th>
                  <th className="py-3 px-3">Timetable</th>
                  <th className="py-3 px-3 text-right">Sessions</th>
                  <th className="py-3 px-3">Joined</th>
                  <th className="py-3 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#161616] font-mono">
                {data.users.map((u) => (
                  <tr key={u.id} className="hover:bg-white/[0.02] transition-colors align-top">
                    <td className="py-3 px-3 max-w-[260px]">
                      <div className="text-white font-semibold truncate" title={u.name}>{u.name || '—'}</div>
                      <div className="text-[#aaaaaa] truncate" title={u.email}>{u.email || 'email not synced yet'}</div>
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 bg-[#161616] border border-[#333333] text-[10px] font-bold uppercase text-white">
                        {u.provider === 'google' ? 'Google' : u.provider === 'email' ? 'Email' : u.provider}
                      </span>
                    </td>
                    <td className="py-3 px-3"><Check on={u.has_barcode} title={u.barcode} /></td>
                    <td className="py-3 px-3"><Check on={u.has_face} title={u.has_face ? fmtDate(u.face_trained_at) : ''} /></td>
                    <td className="py-3 px-3"><Check on={u.has_timetable} /></td>
                    <td className="py-3 px-3 text-right">
                      <div className="text-white font-bold">{u.sessions}</div>
                      <div className="text-[10px] text-[#666666]" title={fmtDateTime(u.last_session_at)}>
                        {u.last_session_at ? `last ${fmtDate(u.last_session_at)}` : 'never at mirror'}
                      </div>
                    </td>
                    <td className="py-3 px-3 text-[#aaaaaa]">{fmtDate(u.created_at)}</td>
                    <td className="py-3 px-3">
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {u.has_face && (
                          <button onClick={() => setPending({ user: u, action: 'face' })}
                            className="px-2 py-1 border border-[#333333] text-[10px] uppercase font-bold text-[#d0d0d0] hover:text-white hover:border-white cursor-pointer">
                            Face
                          </button>
                        )}
                        {u.has_barcode && (
                          <button onClick={() => setPending({ user: u, action: 'barcode' })}
                            className="px-2 py-1 border border-[#333333] text-[10px] uppercase font-bold text-[#d0d0d0] hover:text-white hover:border-white cursor-pointer">
                            ID
                          </button>
                        )}
                        {u.has_timetable && (
                          <button onClick={() => setPending({ user: u, action: 'timetable' })}
                            className="px-2 py-1 border border-[#333333] text-[10px] uppercase font-bold text-[#d0d0d0] hover:text-white hover:border-white cursor-pointer">
                            Timetable
                          </button>
                        )}
                        {u.id !== me?.id && (
                          <button onClick={() => setPending({ user: u, action: 'delete' })}
                            className="px-2 py-1 border border-red-500/40 text-[10px] uppercase font-bold text-red-300 hover:bg-red-950/40 cursor-pointer">
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <AnimatePresence>
        {pending && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[90] bg-black/80 flex items-center justify-center p-6"
            role="dialog" aria-modal="true"
          >
            <div className="max-w-md w-full bg-[#0a0a0a] border border-[#331111] rounded-none p-7 font-mono">
              <h2 className="text-sm font-bold text-white uppercase tracking-wider mb-3">
                {ACTIONS[pending.action].label}?
              </h2>
              <p className="text-xs text-[#aaaaaa] leading-relaxed mb-3">
                This permanently removes the {ACTIONS[pending.action].what} for{' '}
                <span className="text-white">{pending.user.email || pending.user.name || pending.user.id}</span>.
                It cannot be undone.
              </p>
              <p className="text-xs text-[#888888] leading-relaxed mb-6">
                They will see a message saying it was removed by an administrator, with {contactEmail} to contact if it was a mistake.
              </p>
              <div className="flex gap-3">
                <button onClick={() => setPending(null)} disabled={working}
                  className="flex-1 py-2.5 border border-[#333333] text-xs font-bold uppercase text-white hover:border-white cursor-pointer disabled:opacity-50">
                  Cancel
                </button>
                <button onClick={runAction} disabled={working}
                  className="flex-1 py-2.5 bg-red-600 hover:bg-red-500 text-xs font-bold uppercase text-white cursor-pointer disabled:opacity-50">
                  {working ? 'Removing…' : 'Remove'}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
