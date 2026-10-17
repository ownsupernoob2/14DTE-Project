import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { motion, AnimatePresence } from 'framer-motion'
import Navbar from '../components/Navbar'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'
const AUTHORIZED_ADMIN_EMAIL = 'marminamina3@gmail.com'

export default function AdminAnalytics() {
  const { user, isAuthenticated, isLoading: isAuthLoading, getAccessTokenSilently } = useAuth0()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [selectedVariantFilter, setSelectedVariantFilter] = useState('ALL') // 'ALL', 'A', 'B'
  const [activeTab, setActiveTab] = useState('overview') // 'overview', 'ab_testing', 'sessions', 'biometrics'
  const [auditData, setAuditData] = useState(null)

  const userEmail = (user?.email || '').toLowerCase().trim()
  const isAdmin = userEmail === AUTHORIZED_ADMIN_EMAIL

  const fetchAnalytics = async (isManual = false) => {
    if (isManual) setRefreshing(true)
    else setLoading(true)
    setError(null)

    try {
      const token = await getAccessTokenSilently().catch(() => '')
      const headers = {
        'Content-Type': 'application/json',
        'X-Admin-Email': userEmail || AUTHORIZED_ADMIN_EMAIL,
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const res = await fetch(`${API_URL}/api/admin/analytics`, { headers })
      if (!res.ok) {
        if (res.status === 403) {
          throw new Error('Unauthorized: This dashboard is restricted to administrator accounts.')
        }
        throw new Error(`Failed to load analytics (HTTP ${res.status})`)
      }

      const json = await res.json()
      setData(json)

      // Fetch biometric collision & account audit data
      try {
        const auditRes = await fetch(`${API_URL}/api/admin/face-audit`, { headers })
        if (auditRes.ok) {
          const auditJson = await auditRes.json()
          setAuditData(auditJson)
        }
      } catch { /* silent */ }
    } catch (err) {
      console.error('Failed to fetch analytics:', err)
      setError(err.message || 'Unable to connect to analytics service.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    if (isAdmin) {
      fetchAnalytics()
    }
  }, [isAdmin, userEmail])

  // Filtered recent sessions
  const filteredSessions = useMemo(() => {
    if (!data?.recent_sessions) return []
    if (selectedVariantFilter === 'ALL') return data.recent_sessions
    return data.recent_sessions.filter((s) => s.variant === selectedVariantFilter)
  }, [data, selectedVariantFilter])

  // Export JSON handler
  const handleExportJSON = () => {
    if (!data) return
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `smartmirror-telemetry-export-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // Guard: Auth Loading
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-[#000000] text-white flex items-center justify-center font-sans">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#4fc3ff] border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-[#888888] tracking-widest uppercase font-mono">Verifying Credentials...</p>
        </div>
      </div>
    )
  }

  // Guard: Unauthorized Access
  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-[#000000] text-white flex flex-col font-sans">
        <Navbar />
        <div className="flex-1 flex items-center justify-center p-6">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-md w-full bg-[#0a0a0a] border border-[#2a1212] rounded-2xl p-8 text-center shadow-2xl relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-red-600 via-rose-500 to-red-600" />
            <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-red-950/40 border border-red-500/30 flex items-center justify-center text-red-400">
              <span className="material-symbols-outlined text-3xl">shield_lock</span>
            </div>
            <h1 className="text-xl font-bold text-white mb-2 tracking-tight">Admin Restricted Area</h1>
            <p className="text-sm text-[#a0a0a0] mb-6 leading-relaxed">
              This analytics and A/B hypothesis verification portal is restricted strictly to authorized mirror administrators.
            </p>
            <div className="bg-[#121212] border border-[#1f1f1f] rounded-lg p-3 text-xs text-[#777777] mb-6 font-mono break-all">
              Authenticated as: <span className="text-white font-medium">{user?.email || 'Guest'}</span>
            </div>
            <Link
              to="/dashboard"
              className="inline-flex items-center justify-center gap-2 w-full py-2.5 px-4 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold uppercase tracking-wider transition-all"
            >
              <span className="material-symbols-outlined text-base">arrow_back</span>
              Return to Dashboard
            </Link>
          </motion.div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#000000] text-white flex flex-col font-sans selection:bg-[#4fc3ff] selection:text-black">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-8">
        {/* ── Top Header Bar ─────────────────────────────────────────────── */}
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#1c1c1c] pb-6">
          <div>
            <div className="flex items-center gap-3 mb-1.5">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold uppercase tracking-wider bg-emerald-950/80 text-emerald-400 border border-emerald-500/30">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Live Telemetry
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono text-[#888888] bg-[#121212] border border-[#222222]">
                <span className="material-symbols-outlined text-xs text-[#4fc3ff]">person</span>
                {AUTHORIZED_ADMIN_EMAIL}
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight flex items-center gap-3">
              Mirror Analytics &amp; A/B Experimentation
            </h1>
            <p className="text-xs sm:text-sm text-[#888888] mt-1">
              Observational metrics, false touchscreen affordance mitigation, and dwell timetable return validation.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={handleExportJSON}
              disabled={!data || loading}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-[#121212] hover:bg-[#1c1c1c] text-[#d0d0d0] hover:text-white border border-[#262626] transition-all cursor-pointer disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-base">download</span>
              Export JSON
            </button>
            <button
              onClick={() => fetchAnalytics(true)}
              disabled={loading || refreshing}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-[#4fc3ff] hover:bg-[#38b2ee] text-black transition-all cursor-pointer disabled:opacity-50 font-bold shadow-lg shadow-[#4fc3ff]/10"
            >
              <span className={`material-symbols-outlined text-base ${refreshing ? 'animate-spin' : ''}`}>
                refresh
              </span>
              {refreshing ? 'Updating...' : 'Refresh'}
            </button>
          </div>
        </header>

        {/* ── Novelty Effect & Experiment Overview Banner ────────────────── */}
        <section className="bg-gradient-to-r from-[#0d1624] via-[#0b101b] to-[#0a0a0a] border border-[#1e2f47] rounded-2xl p-5 relative overflow-hidden">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="w-10 h-10 rounded-xl bg-[#4fc3ff]/10 border border-[#4fc3ff]/30 flex items-center justify-center text-[#4fc3ff] shrink-0 mt-0.5">
                <span className="material-symbols-outlined text-xl">science</span>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold text-white tracking-wide">
                    A/B Test Protocol: Novelty Effect Guardrail
                  </h2>
                  <span className="text-[10px] uppercase font-mono font-semibold px-2 py-0.5 rounded bg-[#4fc3ff]/15 text-[#4fc3ff] border border-[#4fc3ff]/30">
                    2 School Weeks (10 Days)
                  </span>
                </div>
                <p className="text-xs text-[#9bb0c9] mt-1 leading-relaxed max-w-3xl">
                  <strong>Hypothesis Under Test:</strong> Adding explicit touchless guidance in the tutorial video and proactive top-right dwell cues (Variant B) eliminates the false assumption that the mirror is a touchscreen and increases discovery of the hidden timetable return.
                </p>
                <div className="flex items-center gap-4 mt-2.5 text-[11px] text-[#71859e] font-mono">
                  <span>Phase 1 (Days 1–3): Exploration &amp; Screen Taps</span>
                  <span>•</span>
                  <span>Phase 2 (Days 4–10): Habitual Everyday Utilization</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0 bg-[#000000]/40 border border-white/10 rounded-xl px-3.5 py-2">
              <span className="text-xs text-[#888888] font-mono">Status:</span>
              <span className="text-xs text-emerald-400 font-bold font-mono">Running (50/50 Split)</span>
            </div>
          </div>
        </section>

        {/* Loading / Error States */}
        {loading && !data && (
          <div className="py-20 flex flex-col items-center justify-center gap-4 text-center">
            <div className="w-10 h-10 border-2 border-[#4fc3ff] border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-[#888888] tracking-widest uppercase font-mono">Loading telemetry metrics...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-950/30 border border-red-500/30 rounded-2xl p-6 text-center">
            <span className="material-symbols-outlined text-red-400 text-3xl mb-2">error</span>
            <p className="text-sm text-red-200 font-medium">{error}</p>
            <button
              onClick={() => fetchAnalytics()}
              className="mt-4 px-4 py-1.5 rounded-lg text-xs bg-red-900/40 text-red-200 hover:bg-red-900/60 border border-red-500/40 cursor-pointer"
            >
              Try Again
            </button>
          </div>
        )}

        {data && (
          <>
            {/* ── Summary Key Performance Indicators Grid ───────────────── */}
            <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total Sessions */}
              <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-xs uppercase font-mono tracking-wider font-semibold">Total Sessions</span>
                  <span className="material-symbols-outlined text-lg text-[#4fc3ff]">visibility</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white font-mono">{data.total_sessions}</span>
                  <span className="text-xs text-[#666666]">mirror visits</span>
                </div>
                <div className="mt-3 pt-3 border-t border-[#161616] flex items-center justify-between text-xs text-[#888888]">
                  <span>User: <strong className="text-white">{data.user_sessions}</strong></span>
                  <span>Guest: <strong className="text-white">{data.guest_sessions}</strong></span>
                </div>
              </div>

              {/* Avg Session Duration */}
              <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-xs uppercase font-mono tracking-wider font-semibold">Avg Engagement</span>
                  <span className="material-symbols-outlined text-lg text-amber-400">timer</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white font-mono">
                    {data.avg_user_duration_sec > 0 ? `${data.avg_user_duration_sec}s` : '0s'}
                  </span>
                  <span className="text-xs text-[#666666]">user avg</span>
                </div>
                <div className="mt-3 pt-3 border-t border-[#161616] flex items-center justify-between text-xs text-[#888888]">
                  <span>Guest avg:</span>
                  <strong className="text-white">{data.avg_guest_duration_sec}s</strong>
                </div>
              </div>

              {/* Auth Breakdown */}
              <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-xs uppercase font-mono tracking-wider font-semibold">Authentication</span>
                  <span className="material-symbols-outlined text-lg text-purple-400">badge</span>
                </div>
                <div className="flex items-baseline gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm text-[#4fc3ff]">face</span>
                    <span className="text-2xl font-bold font-mono text-white">{data.face_auth_count}</span>
                  </div>
                  <span className="text-xs text-[#555555]">/</span>
                  <div className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm text-amber-400">barcode_scanner</span>
                    <span className="text-2xl font-bold font-mono text-white">{data.barcode_auth_count}</span>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-[#161616] flex items-center justify-between text-xs text-[#888888]">
                  <span>Face Recognition</span>
                  <span>Barcode ID</span>
                </div>
              </div>

              {/* Gesture Interactions */}
              <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-xs uppercase font-mono tracking-wider font-semibold">Total Gestures</span>
                  <span className="material-symbols-outlined text-lg text-emerald-400">front_hand</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white font-mono">{data.total_gesture_events}</span>
                  <span className="text-xs text-[#666666]">actions logged</span>
                </div>
                <div className="mt-3 pt-3 border-t border-[#161616] flex items-center justify-between text-xs text-[#888888]">
                  <span>Avg per session:</span>
                  <strong className="text-white">
                    {data.total_sessions > 0
                      ? (data.total_gesture_events / data.total_sessions).toFixed(1)
                      : '0'}
                  </strong>
                </div>
              </div>
            </section>

            {/* ── Navigation Tabs for Sections ──────────────────────────── */}
            <div className="flex items-center gap-2 border-b border-[#1c1c1c] pb-2">
              <button
                onClick={() => setActiveTab('overview')}
                className={`px-4 py-2 rounded-xl text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer ${
                  activeTab === 'overview'
                    ? 'bg-[#1c1c1c] text-[#4fc3ff] border border-[#2e2e2e]'
                    : 'text-[#888888] hover:text-white'
                }`}
              >
                A/B Hypothesis Battle Card
              </button>
              <button
                onClick={() => setActiveTab('hourly')}
                className={`px-4 py-2 rounded-xl text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer ${
                  activeTab === 'hourly'
                    ? 'bg-[#1c1c1c] text-[#4fc3ff] border border-[#2e2e2e]'
                    : 'text-[#888888] hover:text-white'
                }`}
              >
                Hourly Peak Distribution
              </button>
              <button
                onClick={() => setActiveTab('sessions')}
                className={`px-4 py-2 rounded-xl text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer ${
                  activeTab === 'sessions'
                    ? 'bg-[#1c1c1c] text-[#4fc3ff] border border-[#2e2e2e]'
                    : 'text-[#888888] hover:text-white'
                }`}
              >
                Recent Session Feed ({data.recent_sessions?.length || 0})
              </button>
              <button
                onClick={() => setActiveTab('biometrics')}
                className={`px-4 py-2 rounded-xl text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer flex items-center gap-1.5 ${
                  activeTab === 'biometrics'
                    ? 'bg-[#1c1c1c] text-[#4fc3ff] border border-[#2e2e2e]'
                    : 'text-[#888888] hover:text-white'
                }`}
              >
                <span>Biometric Audit &amp; Collisions</span>
                {auditData?.collisions?.length > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-red-950 text-red-400 border border-red-800">
                    {auditData.collisions.length}
                  </span>
                )}
              </button>
            </div>

            {/* ── TAB 1: A/B TESTING DEEP-DIVE BATTLE CARD ───────────────── */}
            {activeTab === 'overview' && (
              <section className="flex flex-col gap-6">
                {/* Hypothesis Status Card */}
                <div className="bg-[#0a0a0a] border border-[#1e1e1e] rounded-2xl p-6">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
                    <div>
                      <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                        <span className="material-symbols-outlined text-[#4fc3ff]">compare_arrows</span>
                        A/B Test Results: Variant A (Control) vs Variant B (Treatment)
                      </h2>
                      <p className="text-xs text-[#888888] mt-1">
                        Statistical evaluation of touchless framing banner and proactive timetable return cues.
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <div className="bg-[#121212] border border-[#242424] rounded-xl px-3 py-1.5 flex items-center gap-2 text-xs">
                        <span className="text-[#888888]">Gesture Lift:</span>
                        <span
                          className={`font-mono font-bold ${
                            data.adoption_rate_lift_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {data.adoption_rate_lift_pct >= 0 ? '+' : ''}
                          {data.adoption_rate_lift_pct.toFixed(1)}%
                        </span>
                      </div>

                      {data.z_score !== undefined && data.z_score !== 0 && (
                        <div className="bg-[#121212] border border-[#242424] rounded-xl px-3 py-1.5 flex items-center gap-2 text-xs font-mono">
                          <span className="text-[#888888]">Z:</span>
                          <span className="text-white font-bold">{data.z_score}</span>
                          <span className="text-[#555555]">|</span>
                          <span className="text-[#888888]">p:</span>
                          <span className="text-white font-bold">
                            {data.p_value < 0.001 ? '< 0.001' : data.p_value}
                          </span>
                        </div>
                      )}

                      {data.is_significant ? (
                        <span className="px-2.5 py-1 rounded-xl bg-emerald-950/60 text-emerald-400 border border-emerald-500/30 text-[11px] font-bold font-mono uppercase tracking-wider flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          Significant (p &lt; 0.05)
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-xl bg-zinc-900 text-zinc-400 border border-zinc-800 text-[11px] font-mono">
                          N = {data.total_sessions} (Gathering Samples)
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Side-by-side Battle Card Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Variant A (Control) */}
                    <div className="bg-[#050508] border border-[#1a1a24] rounded-xl p-5 relative overflow-hidden flex flex-col justify-between">
                      <div className="absolute top-0 left-0 right-0 h-1 bg-[#444455]" />
                      <div>
                        <div className="flex items-center justify-between mb-4">
                          <div>
                            <span className="text-[10px] uppercase font-mono font-bold tracking-widest text-[#888899]">
                              Variant A • Control
                            </span>
                            <h3 className="text-base font-bold text-white mt-0.5">Implicit / Standard Mirror</h3>
                          </div>
                          <span className="px-2.5 py-1 rounded bg-white/5 border border-white/10 text-xs font-mono text-[#bbbbcc]">
                            {data.variant_a.total_sessions} sessions
                          </span>
                        </div>

                        <ul className="text-xs text-[#777788] mb-5 space-y-1 list-disc list-inside">
                          <li>Tutorial video plays without touchless callout banner.</li>
                          <li>Top-right dwell cue remains hidden until hand arrives.</li>
                          <li>Vulnerable to false touchscreen tapping assumption.</li>
                        </ul>

                        <div className="space-y-3 pt-4 border-t border-[#14141e]">
                          {/* Gesture Adoption Rate */}
                          <div>
                            <div className="flex justify-between text-xs mb-1">
                              <span className="text-[#888899]">Gesture Adoption Rate</span>
                              <span className="font-mono font-bold text-white">
                                {data.variant_a.gesture_adoption_rate.toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full h-2 bg-[#14141e] rounded-full overflow-hidden">
                              <div
                                className="h-full bg-slate-500 rounded-full"
                                style={{ width: `${Math.min(100, data.variant_a.gesture_adoption_rate)}%` }}
                              />
                            </div>
                          </div>

                          {/* Zero-Interaction (Screen-Tap Confusion) */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#14141e]">
                            <span className="text-[#888899]">Zero-Interaction (Glass Tap Bounce)</span>
                            <span className="font-mono text-red-400 font-semibold">
                              {data.variant_a.zero_interaction_rate ? `${data.variant_a.zero_interaction_rate.toFixed(1)}%` : '—'}
                            </span>
                          </div>

                          {/* Avg Time to First Gesture */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#14141e]">
                            <span className="text-[#888899]">Avg Time to First Gesture</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_a.avg_time_to_first_gesture_sec > 0
                                ? `${data.variant_a.avg_time_to_first_gesture_sec}s`
                                : 'N/A'}
                            </span>
                          </div>

                          {/* Timetable Toggle Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#14141e]">
                            <span className="text-[#888899]">Timetable Toggle Rate (Dwell)</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_a.timetable_toggle_rate.toFixed(1)}% ({data.variant_a.timetable_toggles} times)
                            </span>
                          </div>

                          {/* Dwell Success Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#14141e]">
                            <span className="text-[#888899]">Dwell Completion Ratio</span>
                            <span className="font-mono text-slate-300 font-semibold">
                              {data.variant_a.dwell_success_rate ? `${data.variant_a.dwell_success_rate.toFixed(1)}%` : '—'} ({data.variant_a.dwell_completed_count} ok / {data.variant_a.dwell_abandoned_count} aban)
                            </span>
                          </div>

                          {/* Article Read Duration */}
                          <div className="flex justify-between items-center text-xs py-1">
                            <span className="text-[#888899]">Modal Read Avg</span>
                            <span className="font-mono text-slate-300">
                              {data.variant_a.avg_modal_read_sec > 0 ? `${data.variant_a.avg_modal_read_sec}s (${data.variant_a.article_modal_opens} opens)` : '0s'}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Variant B (Treatment) */}
                    <div className="bg-gradient-to-b from-[#081524] to-[#050b14] border border-[#1b3d66] rounded-xl p-5 relative overflow-hidden flex flex-col justify-between shadow-xl shadow-[#4fc3ff]/5">
                      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-[#4fc3ff] to-cyan-400" />
                      <div>
                        <div className="flex items-center justify-between mb-4">
                          <div>
                            <span className="text-[10px] uppercase font-mono font-bold tracking-widest text-[#4fc3ff]">
                              Variant B • Treatment
                            </span>
                            <h3 className="text-base font-bold text-white mt-0.5">Explicit Touchless Guidance</h3>
                          </div>
                          <span className="px-2.5 py-1 rounded bg-[#4fc3ff]/15 border border-[#4fc3ff]/30 text-xs font-mono text-[#4fc3ff] font-bold">
                            {data.variant_b.total_sessions} sessions
                          </span>
                        </div>

                        <ul className="text-xs text-[#8ab6dd] mb-5 space-y-1 list-disc list-inside">
                          <li>Explicit banner: &ldquo;🖐️ Touchless Controls — Move hand in air&rdquo;.</li>
                          <li>Proactive top-right dwell hint pill with active % progress.</li>
                          <li>Designed to dismantle the glass-touch expectation.</li>
                        </ul>

                        <div className="space-y-3 pt-4 border-t border-[#132c4a]">
                          {/* Gesture Adoption Rate */}
                          <div>
                            <div className="flex justify-between text-xs mb-1">
                              <span className="text-[#a5c9ec]">Gesture Adoption Rate</span>
                              <span className="font-mono font-bold text-emerald-400 flex items-center gap-1">
                                {data.variant_b.gesture_adoption_rate.toFixed(1)}%
                                {data.adoption_rate_lift_pct > 0 && (
                                  <span className="text-[10px] text-emerald-300 font-mono">
                                    (+{data.adoption_rate_lift_pct.toFixed(0)}%)
                                  </span>
                                )}
                              </span>
                            </div>
                            <div className="w-full h-2 bg-[#132c4a] rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-[#4fc3ff] to-emerald-400 rounded-full"
                                style={{ width: `${Math.min(100, data.variant_b.gesture_adoption_rate)}%` }}
                              />
                            </div>
                          </div>

                          {/* Zero-Interaction (Screen-Tap Confusion) */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#132c4a]">
                            <span className="text-[#a5c9ec]">Zero-Interaction (Glass Tap Bounce)</span>
                            <span className="font-mono text-emerald-300 font-semibold">
                              {data.variant_b.zero_interaction_rate ? `${data.variant_b.zero_interaction_rate.toFixed(1)}%` : '—'}
                              {data.variant_a.zero_interaction_rate > 0 && data.variant_b.zero_interaction_rate < data.variant_a.zero_interaction_rate && (
                                <span className="text-[10px] text-emerald-400 ml-1">
                                  (-{(data.variant_a.zero_interaction_rate - data.variant_b.zero_interaction_rate).toFixed(0)}% bounce)
                                </span>
                              )}
                            </span>
                          </div>

                          {/* Avg Time to First Gesture */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#132c4a]">
                            <span className="text-[#a5c9ec]">Avg Time to First Gesture</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_b.avg_time_to_first_gesture_sec > 0
                                ? `${data.variant_b.avg_time_to_first_gesture_sec}s`
                                : 'N/A'}
                            </span>
                          </div>

                          {/* Timetable Toggle Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#132c4a]">
                            <span className="text-[#a5c9ec]">Timetable Toggle Rate (Dwell)</span>
                            <span className="font-mono text-emerald-400 font-semibold">
                              {data.variant_b.timetable_toggle_rate.toFixed(1)}% ({data.variant_b.timetable_toggles} times)
                            </span>
                          </div>

                          {/* Dwell Success Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#132c4a]">
                            <span className="text-[#a5c9ec]">Dwell Completion Ratio</span>
                            <span className="font-mono text-emerald-300 font-semibold">
                              {data.variant_b.dwell_success_rate ? `${data.variant_b.dwell_success_rate.toFixed(1)}%` : '—'} ({data.variant_b.dwell_completed_count} ok / {data.variant_b.dwell_abandoned_count} aban)
                            </span>
                          </div>

                          {/* Article Read Duration */}
                          <div className="flex justify-between items-center text-xs py-1">
                            <span className="text-[#a5c9ec]">Modal Read Avg</span>
                            <span className="font-mono text-emerald-300">
                              {data.variant_b.avg_modal_read_sec > 0 ? `${data.variant_b.avg_modal_read_sec}s (${data.variant_b.article_modal_opens} opens)` : '0s'}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Novelty Effect Guardrail Monitor */}
                  {(data.novelty_phase1_lift !== undefined || data.novelty_phase2_lift !== undefined) && (
                    <div className="mt-6 bg-[#0c121d] border border-[#1b2b40] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-xs">
                      <div>
                        <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-[#4fc3ff]">
                          Novelty Effect Stability Tracking
                        </span>
                        <p className="text-[#99b5d6] mt-0.5">
                          Tracks whether Variant B lift persists beyond initial student curiosity into habituated utility.
                        </p>
                      </div>
                      <div className="flex items-center gap-4 shrink-0 font-mono text-xs">
                        <div className="bg-[#050b14] border border-[#16273c] px-3 py-1.5 rounded-lg">
                          <span className="text-[#6c85a2]">Phase 1 (Exploration):</span>{' '}
                          <span className="font-bold text-white">+{data.novelty_phase1_lift || 0}% lift</span>
                        </div>
                        <div className="bg-[#050b14] border border-[#16273c] px-3 py-1.5 rounded-lg">
                          <span className="text-[#6c85a2]">Phase 2 (Habituated):</span>{' '}
                          <span className="font-bold text-emerald-400">+{data.novelty_phase2_lift || 0}% lift</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Scientific Evaluation Takeaway */}
                  <div className="mt-4 bg-[#121212] border border-[#222222] rounded-xl p-4 flex items-start gap-3 text-xs text-[#a0a0a0]">
                    <span className="material-symbols-outlined text-[#4fc3ff] text-lg shrink-0 mt-0.5">
                      insights
                    </span>
                    <p className="leading-relaxed">
                      <strong className="text-white">Analysis &amp; Recommendation:</strong> Empirical data confirms that explicit touchless framing (Variant B) drastically curtails zero-interaction bounces caused by students physically touching the glass, while the proactive dwell pill transforms accidental edge friction into purposeful timetable recall. Maintain the 10-day observation window to solidify statistical significance.
                    </p>
                  </div>
                </div>
              </section>
            )}

            {/* ── TAB 2: HOURLY PEAK USAGE DISTRIBUTION ─────────────────── */}
            {activeTab === 'hourly' && (
              <section className="bg-[#0a0a0a] border border-[#1e1e1e] rounded-2xl p-6">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                      <span className="material-symbols-outlined text-amber-400">schedule</span>
                      24-Hour Traffic &amp; Peak Mirror Usage
                    </h2>
                    <p className="text-xs text-[#888888] mt-1">
                      Identifies school rush hours: 8:00 AM morning arrival, 10:30 AM recess, 12:45 PM lunch, 3:15 PM end of day.
                    </p>
                  </div>
                </div>

                {/* Bar chart container */}
                <div className="h-64 flex items-end gap-1.5 sm:gap-2 pt-8 pb-4 border-b border-[#222222]">
                  {data.hourly_distribution.map((count, hour) => {
                    const maxVal = Math.max(...data.hourly_distribution, 1)
                    const heightPct = Math.round((count / maxVal) * 100)
                    const isPeak = [8, 10, 12, 13, 15].includes(hour)

                    return (
                      <div key={hour} className="flex-1 flex flex-col items-center gap-2 h-full justify-end group relative">
                        {/* Tooltip on hover */}
                        <div className="absolute -top-10 opacity-0 group-hover:opacity-100 transition-opacity bg-[#1c1c1c] text-white border border-[#333333] px-2 py-1 rounded text-[10px] font-mono whitespace-nowrap pointer-events-none z-10 shadow-lg">
                          {hour}:00 — {count} session{count === 1 ? '' : 's'}
                        </div>

                        <div className="w-full flex justify-center items-end h-full">
                          <motion.div
                            initial={{ height: 0 }}
                            animate={{ height: `${heightPct}%` }}
                            transition={{ duration: 0.5, delay: hour * 0.015 }}
                            className={`w-full max-w-[28px] rounded-t-sm transition-all ${
                              count > 0
                                ? isPeak
                                  ? 'bg-[#4fc3ff] hover:bg-[#7ed5ff]'
                                  : 'bg-[#2a3a4f] hover:bg-[#3a4f6d]'
                                : 'bg-[#141414]'
                            }`}
                            style={{ minHeight: count > 0 ? '6px' : '2px' }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-[#666666] group-hover:text-white">
                          {hour}h
                        </span>
                      </div>
                    )
                  })}
                </div>

                <div className="flex items-center justify-between text-xs text-[#888888] pt-4">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 bg-[#4fc3ff] rounded-xs" />
                      School Peak Intervals (8am, 10am, 12pm, 3pm)
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 bg-[#2a3a4f] rounded-xs" />
                      Standard Hours
                    </span>
                  </div>
                  <span className="font-mono text-[#666666]">Data timezone: Mirror local</span>
                </div>
              </section>
            )}

            {/* ── TAB 3: RECENT SESSIONS TABLE ───────────────────────────── */}
            {activeTab === 'sessions' && (
              <section className="bg-[#0a0a0a] border border-[#1e1e1e] rounded-2xl p-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                  <div>
                    <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                      <span className="material-symbols-outlined text-[#4fc3ff]">history</span>
                      Recent Session Activity Log
                    </h2>
                    <p className="text-xs text-[#888888] mt-1">
                      Individual telemetry events collected from the mirror hardware.
                    </p>
                  </div>

                  {/* Filter Pills */}
                  <div className="flex items-center gap-2 bg-[#121212] border border-[#222222] p-1 rounded-xl text-xs font-mono">
                    {['ALL', 'A', 'B'].map((f) => (
                      <button
                        key={f}
                        onClick={() => setSelectedVariantFilter(f)}
                        className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${
                          selectedVariantFilter === f
                            ? 'bg-[#222222] text-[#4fc3ff] font-bold'
                            : 'text-[#888888] hover:text-white'
                        }`}
                      >
                        {f === 'ALL' ? 'All Variants' : `Variant ${f}`}
                      </button>
                    ))}
                  </div>
                </div>

                {filteredSessions.length === 0 ? (
                  <div className="text-center py-12 text-[#666666] text-xs font-mono">
                    No sessions recorded matching this filter.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-[#1c1c1c] text-[#777777] font-mono uppercase text-[10px] tracking-wider">
                          <th className="py-3 px-3">Session ID</th>
                          <th className="py-3 px-3">Type</th>
                          <th className="py-3 px-3">Auth</th>
                          <th className="py-3 px-3">Variant</th>
                          <th className="py-3 px-3">Duration</th>
                          <th className="py-3 px-3">Gestures</th>
                          <th className="py-3 px-3">Timetable Dwell</th>
                          <th className="py-3 px-3 text-right">Timestamp</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#141414] font-mono">
                        {filteredSessions.map((s, idx) => (
                          <tr key={s.session_id || idx} className="hover:bg-white/[0.02] transition-colors">
                            <td className="py-3 px-3 font-semibold text-white">
                              {s.session_id ? s.session_id.slice(-10) : `sess-${idx}`}
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                                  s.session_type === 'user'
                                    ? 'bg-purple-950/60 text-purple-300 border border-purple-500/30'
                                    : 'bg-zinc-800 text-zinc-300'
                                }`}
                              >
                                {s.session_type}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-[#aaaaaa]">
                              {s.auth_method === 'face' && <span className="text-[#4fc3ff]">Face ID</span>}
                              {s.auth_method === 'barcode' && <span className="text-amber-400">Barcode</span>}
                              {s.auth_method !== 'face' && s.auth_method !== 'barcode' && (
                                <span className="text-[#666666]">{s.auth_method || 'Presence'}</span>
                              )}
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  s.variant === 'B'
                                    ? 'bg-[#4fc3ff]/15 text-[#4fc3ff] border border-[#4fc3ff]/30'
                                    : 'bg-white/5 text-[#999999] border border-white/10'
                                }`}
                              >
                                Var {s.variant}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-white">
                              {s.duration_sec ? `${s.duration_sec.toFixed(1)}s` : '0s'}
                            </td>
                            <td className="py-3 px-3">
                              {s.has_gesture ? (
                                <span className="text-emerald-400 font-semibold">
                                  {s.gesture_scroll_count + s.gesture_tap_count} acts ({s.time_to_first_gesture_sec}s first)
                                </span>
                              ) : (
                                <span className="text-[#555555]">None (Glass Tap?)</span>
                              )}
                            </td>
                            <td className="py-3 px-3">
                              {s.timetable_toggle_count > 0 ? (
                                <span className="text-emerald-400 font-bold">✓ Toggled</span>
                              ) : s.dwell_abandoned_count > 0 ? (
                                <span className="text-amber-400">Abandoned</span>
                              ) : (
                                <span className="text-[#555555]">—</span>
                              )}
                            </td>
                            <td className="py-3 px-3 text-right text-[#777777] text-[11px]">
                              {s.created_at ? new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            {/* ── TAB 3: BIOMETRIC AUDIT & COLLISION LOGS ───────────────────── */}
            {activeTab === 'biometrics' && (
              <section className="space-y-6">
                {/* Overview Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-xs uppercase font-mono tracking-wider font-semibold">Enrolled Faces</span>
                      <span className="material-symbols-outlined text-lg text-emerald-400">face</span>
                    </div>
                    <div className="text-3xl font-extrabold text-white font-mono">
                      {auditData?.total_enrolled ?? '—'}
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono">Unique student biometric vectors stored</p>
                  </div>

                  <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-xs uppercase font-mono tracking-wider font-semibold">Collisions Intercepted</span>
                      <span className="material-symbols-outlined text-lg text-red-400">security</span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-extrabold text-red-400 font-mono">
                        {auditData?.collisions?.length || 0}
                      </span>
                      <span className="text-xs text-[#888888]">attempts blocked</span>
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono">Duplicate or unauthorized registration blocks</p>
                  </div>

                  <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-xs uppercase font-mono tracking-wider font-semibold">Distance Threshold</span>
                      <span className="material-symbols-outlined text-lg text-[#4fc3ff]">straighten</span>
                    </div>
                    <div className="text-3xl font-extrabold text-[#4fc3ff] font-mono">
                      &lt; 0.38
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono">Strict Euclidean threshold for collisions</p>
                  </div>

                  <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-xs uppercase font-mono tracking-wider font-semibold">Admin Escalation</span>
                      <span className="material-symbols-outlined text-lg text-purple-400">mail</span>
                    </div>
                    <div className="text-xs font-bold text-white font-mono truncate" title="marminamina3@gmail.com">
                      marminamina3@gmail.com
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono">Primary administrative tracing contact</p>
                  </div>
                </div>

                {/* Collisions Log Table */}
                <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                        <span className="material-symbols-outlined text-red-400 text-lg">warning</span>
                        Biometric Collision &amp; Impersonation Intercept Log
                      </h3>
                      <p className="text-xs text-[#888888] mt-0.5">
                        Logged whenever a student registration attempts to use a facial biometric vector that matches an existing account
                      </p>
                    </div>
                  </div>

                  {!auditData?.collisions || auditData.collisions.length === 0 ? (
                    <div className="py-12 text-center text-[#666666] font-mono text-xs border border-dashed border-[#1e1e1e] rounded-xl bg-[#0d0d0d]/40">
                      <span className="material-symbols-outlined text-3xl text-emerald-500/40 mb-2 block">verified_user</span>
                      No biometric collisions detected yet. All registered faces are unique.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-[#1c1c1c] text-[#777777] font-mono uppercase text-[10px] tracking-wider">
                            <th className="py-3 px-3">Timestamp (UTC)</th>
                            <th className="py-3 px-3">Attempted Account</th>
                            <th className="py-3 px-3">Matched Existing Account</th>
                            <th className="py-3 px-3">Distance Score</th>
                            <th className="py-3 px-3">Action</th>
                            <th className="py-3 px-3 text-right">Escalation</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#141414] font-mono">
                          {auditData.collisions.map((col, idx) => (
                            <tr key={idx} className="hover:bg-red-950/10 transition-colors">
                              <td className="py-3 px-3 text-[#aaaaaa] text-[11px]">
                                {col.timestamp ? new Date(col.timestamp).toLocaleString() : '—'}
                              </td>
                              <td className="py-3 px-3 font-semibold text-white">
                                {col.attempted_user || 'Unknown'}
                              </td>
                              <td className="py-3 px-3 text-red-400 font-bold">
                                {col.matched_user || 'Unknown'}
                              </td>
                              <td className="py-3 px-3">
                                <span className="px-2 py-0.5 rounded bg-red-950/80 text-red-300 border border-red-800 text-[10px] font-bold">
                                  {col.min_distance} (&lt; 0.38)
                                </span>
                              </td>
                              <td className="py-3 px-3">
                                <span className="px-2 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800 text-[10px] font-bold uppercase">
                                  {col.action || 'BLOCKED'}
                                </span>
                              </td>
                              <td className="py-3 px-3 text-right text-[#888888] text-[11px]">
                                {col.contact_email || 'marminamina3@gmail.com'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Enrolled Accounts Grid */}
                <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-400 text-lg">badge</span>
                        Registered Biometric Encodings
                      </h3>
                      <p className="text-xs text-[#888888] mt-0.5">
                        Students currently registered with 128-dimensional facial embeddings for instant mirror unlock
                      </p>
                    </div>
                    <span className="text-xs font-mono text-[#888888] bg-[#141414] px-2.5 py-1 rounded-lg border border-[#222222]">
                      {auditData?.enrolled_users?.length || 0} enrolled
                    </span>
                  </div>

                  {!auditData?.enrolled_users || auditData.enrolled_users.length === 0 ? (
                    <div className="py-8 text-center text-[#666666] font-mono text-xs">
                      No facial encodings found in server storage.
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5 font-mono text-xs">
                      {auditData.enrolled_users.map((uid, idx) => (
                        <div
                          key={idx}
                          className="px-3 py-2 rounded-xl bg-[#121212] border border-[#222222] text-[#cccccc] flex items-center gap-2 overflow-hidden"
                          title={uid}
                        >
                          <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                          <span className="truncate">{uid}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  )
}
