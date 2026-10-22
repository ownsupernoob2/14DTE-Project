import { useState, useEffect, useRef, useCallback } from 'react'
import { useMe } from '../../contexts/MeContext'

const LOG_TYPES = [
  { id: 'mirror', label: 'Mirror UI', file: 'mirror.log', icon: 'desktop_windows' },
  { id: 'face', label: 'Face Daemon', file: 'face_daemon.log', icon: 'face' },
  { id: 'gesture', label: 'Gesture Daemon', file: 'gesture_daemon.log', icon: 'front_hand' },
  { id: 'rpicam', label: 'RPiCam Video', file: 'rpicam.log', icon: 'videocam' },
  { id: 'ffmpeg', label: 'FFmpeg Stream', file: 'ffmpeg.log', icon: 'sync' },
  { id: 'start', label: 'Startup', file: 'start.log', icon: 'power_settings_new' },
  { id: 'server', label: 'Server', file: 'server.log', icon: 'dns' },
]

const ago = (unix) => {
  if (!unix) return 'never'
  const s = Math.max(0, Math.round(Date.now() / 1000 - unix))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return new Date(unix * 1000).toLocaleDateString()
}

export default function AdminLogs() {
  const { authFetch } = useMe()
  const [activeLog, setActiveLog] = useState('mirror')
  const [mirrorId, setMirrorId] = useState('')      // '' = most recently active
  const [mirrors, setMirrors] = useState([])
  const [logContent, setLogContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [copied, setCopied] = useState(false)
  const logContainerRef = useRef(null)

  const fetchLogs = useCallback(async (logName, isBackground = false) => {
    if (!isBackground) setLoading(true)
    try {
      const res = await authFetch(
        `/api/admin/logs?name=${encodeURIComponent(logName)}&mirror=${encodeURIComponent(mirrorId)}`)
      if (res.ok) {
        const data = await res.json()
        setLogContent(data.content || 'Log is empty.')
        setLastUpdated(data.updated_at || null)
        setMirrors(data.mirrors || [])
      } else {
        const err = await res.json().catch(() => ({}))
        setLogContent(err.error || `Failed to fetch logs (HTTP ${res.status}).`)
      }
    } catch (err) {
      setLogContent(`Error fetching log: ${err.message}`)
    } finally {
      if (!isBackground) setLoading(false)
    }
  }, [authFetch, mirrorId])

  // Fetch when active log type changes
  useEffect(() => {
    fetchLogs(activeLog, false)
  }, [activeLog, fetchLogs])

  // Auto-refresh interval (every 3 seconds)
  useEffect(() => {
    let interval = null
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchLogs(activeLog, true)
      }, 5000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [autoRefresh, activeLog, fetchLogs])

  // Auto-scroll terminal to bottom when new content arrives
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logContent])

  const handleCopy = () => {
    if (!logContent) return
    navigator.clipboard.writeText(logContent).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const lineCount = logContent ? logContent.split('\n').length : 0

  return (
    <section className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6 flex flex-col gap-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-[#1c1c1c]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-none bg-[#161616] border border-[#333333] flex items-center justify-center text-white shrink-0">
            <span className="material-symbols-outlined text-xl">terminal</span>
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xs font-bold text-white uppercase tracking-wider">
                System Daemon &amp; Hardware Logs
              </h2>
              <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-none bg-[#15803d]/20 border border-[#22c55e]/40 text-[#22c55e] text-[10px] font-mono font-bold uppercase tracking-wider">
                <span className={`w-1.5 h-1.5 rounded-full bg-[#22c55e] ${autoRefresh ? 'animate-pulse' : ''}`} />
                {autoRefresh ? 'STREAMING ACTIVE' : 'PAUSED'}
              </div>
            </div>
            <p className="text-xs text-[#888888] mt-1 font-mono uppercase tracking-wider">
              The newest lines from each mirror's daemons, sent every 10 seconds while they change.
            </p>
          </div>
        </div>

        {/* Top Controls */}
        <div className="flex items-center gap-3 shrink-0">
          <label className="flex items-center gap-2 text-xs font-mono text-[#aaaaaa] hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-white cursor-pointer"
            />
            <span className="uppercase text-[11px]">Auto-Refresh (5s)</span>
          </label>

          <button
            onClick={() => fetchLogs(activeLog, false)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#161616] hover:bg-[#222222] text-[#d0d0d0] hover:text-white border border-[#333333] hover:border-white text-xs font-mono font-bold uppercase tracking-wider transition-all cursor-pointer disabled:opacity-50"
          >
            <span className={`material-symbols-outlined text-sm ${loading ? 'animate-spin' : ''}`}>
              refresh
            </span>
            Refresh
          </button>
        </div>
      </div>

      {/* ── Which mirror ────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#888888]">
          Mirror
          <select
            value={mirrorId}
            onChange={(e) => setMirrorId(e.target.value)}
            className="bg-[#121212] border border-[#333333] px-2 py-1.5 text-xs text-white font-mono rounded-none normal-case"
          >
            <option value="">Most recently active</option>
            {mirrors.map((m) => (
              <option key={m.id} value={m.id}>{m.id} · last report {ago(m.updated_at)}</option>
            ))}
          </select>
        </label>
        {mirrors.length === 0 && (
          <span className="text-[11px] font-mono text-[#666666]">No mirror has sent logs yet.</span>
        )}
      </div>

      {/* ── Log Type Tabs ───────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        {LOG_TYPES.map((log) => {
          const isSelected = activeLog === log.id
          return (
            <button
              key={log.id}
              onClick={() => setActiveLog(log.id)}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-none text-xs font-mono font-bold uppercase tracking-wider border transition-all cursor-pointer ${
                isSelected
                  ? 'bg-white text-black border-white shadow-sm'
                  : 'bg-[#121212] text-[#888888] hover:text-white border-[#222222] hover:border-[#444444]'
              }`}
            >
              <span className={`material-symbols-outlined text-sm ${isSelected ? 'text-black' : 'text-[#888888]'}`}>
                {log.icon}
              </span>
              <span>{log.label}</span>
              <span className={`text-[10px] opacity-75 font-normal ${isSelected ? 'text-black' : 'text-[#666666]'}`}>
                ({log.file})
              </span>
            </button>
          )
        })}
      </div>

      {/* ── Terminal Window ─────────────────────────────────────────────── */}
      <div className="bg-[#050505] border border-[#222222] rounded-none flex flex-col overflow-hidden">
        {/* Terminal Header Bar */}
        <div className="bg-[#0e0e0e] border-b border-[#1c1c1c] px-4 py-2 flex items-center justify-between text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#ff5f56]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#27c93f]" />
            <span className="text-[#666666] ml-2 font-bold uppercase tracking-wider">
              {LOG_TYPES.find((l) => l.id === activeLog)?.file} — {lineCount} lines
            </span>
          </div>

          <div className="flex items-center gap-4">
            {lastUpdated && (
              <span className="text-[11px] text-[#666666]">
                SENT BY MIRROR {ago(lastUpdated).toUpperCase()}
              </span>
            )}
            <button
              onClick={handleCopy}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#141414] hover:bg-[#202020] text-[#aaaaaa] hover:text-white border border-[#262626] text-[10px] font-mono uppercase tracking-wider transition-all cursor-pointer"
            >
              <span className="material-symbols-outlined text-xs">
                {copied ? 'check' : 'content_copy'}
              </span>
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>

        {/* Log Viewer Container */}
        <pre
          ref={logContainerRef}
          className="p-4 text-xs font-mono text-[#00ff66] bg-[#050505] h-[520px] overflow-y-auto overflow-x-auto whitespace-pre-wrap break-all leading-relaxed select-text scrollbar-thin scrollbar-thumb-[#333333] scrollbar-track-transparent"
        >
          {loading && !logContent ? (
            <span className="text-[#888888] animate-pulse">Streaming log from server...</span>
          ) : (
            logContent || '<Log file is empty>'
          )}
        </pre>
      </div>
    </section>
  )
}
