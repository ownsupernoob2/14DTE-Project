import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { motion, AnimatePresence } from 'framer-motion'
import Navbar from '../components/Navbar'
import UsersPanel from '../components/admin/UsersPanel'
import ScreensaverPanel from '../components/admin/ScreensaverPanel'
import { useMe } from '../contexts/MeContext'
import { API_URL } from '../config'

export default function AdminAnalytics() {
  const { user, isLoading: isAuthLoading } = useAuth0()
  const { me, meChecked, isAdmin, authFetch, contactEmail } = useMe()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [selectedVariantFilter, setSelectedVariantFilter] = useState('ALL') // 'ALL', 'A', 'B'
  const [activeTab, setActiveTab] = useState('overview') // overview | users | screensaver | hourly | sessions | biometrics
  const [auditData, setAuditData] = useState(null)
  const [abConfig, setAbConfig] = useState(() => {
    try {
      const savedMode = localStorage.getItem('smartmirror_ab_mode') || 'auto'
      const savedVar = localStorage.getItem('smartmirror_ab_variant') || 'A'
      return {
        mode: savedMode,
        current_variant: savedVar,
        last_switched: '',
        updated_by: '',
      }
    } catch {
      return {
        mode: 'auto',
        current_variant: 'A',
        last_switched: '',
        updated_by: '',
      }
    }
  })
  const [savingConfig, setSavingConfig] = useState(false)
  const [configFeedback, setConfigFeedback] = useState('')


  const fetchAnalytics = async (isManual = false) => {
    if (isManual) setRefreshing(true)
    else setLoading(true)
    setError(null)

    try {
      const res = await authFetch('/api/admin/analytics')
      if (!res.ok) {
        if (res.status === 403) {
          throw new Error('Unauthorized: This dashboard is restricted to administrator accounts.')
        }
        throw new Error(`Failed to load analytics (HTTP ${res.status})`)
      }

      const json = await res.json()
      setData(json)

      // Fetch dynamic A/B test config safely
      try {
        const cfgRes = await fetch(`${API_URL}/api/analytics/config`)
        if (cfgRes.ok) {
          const cfgJson = await cfgRes.json()
          if (cfgJson && typeof cfgJson === 'object') {
            setAbConfig((prev) => ({
              ...prev,
              ...cfgJson,
              mode: cfgJson.mode || prev?.mode || 'auto',
              current_variant: cfgJson.current_variant || prev?.current_variant || 'A',
            }))
          }
        }
      } catch { /* silent */ }

      // Fetch biometric collision & account audit data safely
      try {
        const auditRes = await authFetch('/api/admin/face-audit')
        if (auditRes.ok) {
          const auditJson = await auditRes.json()
          setAuditData(auditJson)
        } else {
          setAuditData((prev) => prev || { total_enrolled: 0, collisions: [] })
        }
      } catch {
        setAuditData((prev) => prev || { total_enrolled: 0, collisions: [] })
      }
    } catch (err) {
      console.error('Failed to fetch analytics:', err)
      setError(err.message || 'Unable to connect to analytics service.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const handleSwitchABMode = async (newMode) => {
    setSavingConfig(true)
    setConfigFeedback('')

    const targetVariant = newMode === 'force_b' ? 'B' : (newMode === 'force_a' ? 'A' : (abConfig?.current_variant || 'A'))
    setAbConfig((prev) => ({
      ...prev,
      mode: newMode,
      current_variant: targetVariant,
    }))
    try {
      localStorage.setItem('smartmirror_ab_mode', newMode)
      localStorage.setItem('smartmirror_ab_variant', targetVariant)
    } catch { /* silent */ }

    try {
      const res = await authFetch('/api/analytics/config', {
        method: 'POST',
        body: JSON.stringify({ mode: newMode }),
      })
      if (res.ok) {
        const updated = await res.json()
        if (updated && typeof updated === 'object') {
          setAbConfig((prev) => ({
            ...prev,
            ...updated,
            mode: updated.mode || newMode,
            current_variant: updated.current_variant || targetVariant,
          }))
        }
      }
      setConfigFeedback(`Active mode updated to: ${newMode.toUpperCase()}`)
      setTimeout(() => setConfigFeedback(''), 4000)
    } catch (err) {
      console.warn('Config synced locally:', err)
      setConfigFeedback(`Active mode set locally: ${newMode.toUpperCase()}`)
      setTimeout(() => setConfigFeedback(''), 4000)
    } finally {
      setSavingConfig(false)
    }
  }

  useEffect(() => {
    if (isAdmin) {
      fetchAnalytics()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin])

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
  if (isAuthLoading || (!me && !meChecked)) {
    return (
      <div className="min-h-screen bg-[#000000] text-white flex items-center justify-center font-mono">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-white border-t-transparent animate-spin rounded-none" />
          <p className="text-xs text-[#888888] tracking-widest uppercase">Verifying Credentials...</p>
        </div>
      </div>
    )
  }

  // Guard: Unauthorized Access
  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-[#000000] text-white flex flex-col font-mono">
        <Navbar />
        <div className="flex-1 flex items-center justify-center p-6">
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-md w-full bg-[#0a0a0a] border border-[#331111] rounded-none p-8 text-center shadow-2xl relative"
          >
            <div className="w-16 h-16 mx-auto mb-5 rounded-none bg-red-950/40 border border-red-500/30 flex items-center justify-center text-red-400">
              <span className="material-symbols-outlined text-3xl">shield_lock</span>
            </div>
            <h1 className="text-xl font-bold text-white mb-2 uppercase tracking-tight">Admin Restricted Area</h1>
            <p className="text-xs text-[#888888] mb-6 leading-relaxed uppercase tracking-wider">
              This analytics and A/B hypothesis verification portal is restricted strictly to authorized mirror administrators.
            </p>
            <div className="bg-[#121212] border border-[#222222] rounded-none p-3 text-xs text-[#777777] mb-6 font-mono break-all">
              Authenticated as: <span className="text-white font-medium">{user?.email || 'Guest'}</span>
            </div>
            <Link
              to="/dashboard"
              className="inline-flex items-center justify-center gap-2 w-full py-3 px-4 bg-white text-black hover:bg-[#e0e0e0] text-xs font-bold uppercase tracking-wider rounded-none transition-colors"
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
    <div className="min-h-screen bg-[#000000] text-white flex flex-col font-mono selection:bg-white selection:text-black">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-8">
        {/* ── Top Header Bar ─────────────────────────────────────────────── */}
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#222222] pb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-none text-[10px] font-mono font-bold uppercase tracking-wider bg-[#141414] text-white border border-[#333333]">
                <span className="w-1.5 h-1.5 rounded-none bg-white animate-pulse" />
                Live Telemetry
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-none text-[10px] font-mono text-[#888888] bg-[#0e0e0e] border border-[#222222]">
                <span className="material-symbols-outlined text-xs text-[#aaaaaa]">person</span>
                {me?.email}
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight uppercase">
              Mirror Analytics &amp; A/B Experimentation
            </h1>
            <p className="text-xs text-[#888888] mt-1 uppercase tracking-wider">
              Observational metrics, touchless control affordances, and timetable dwell return validation.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={handleExportJSON}
              disabled={!data || loading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-none text-xs font-bold uppercase tracking-wider bg-[#121212] hover:bg-[#1c1c1c] text-[#d0d0d0] hover:text-white border border-[#333333] hover:border-white transition-all cursor-pointer disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-base">download</span>
              Export JSON
            </button>
            <button
              onClick={() => fetchAnalytics(true)}
              disabled={loading || refreshing}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-none text-xs font-bold uppercase tracking-wider bg-white hover:bg-[#e0e0e0] text-black transition-all cursor-pointer disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-base ${refreshing ? 'animate-spin' : ''}`}>
                refresh
              </span>
              {refreshing ? 'Updating...' : 'Refresh'}
            </button>
          </div>
        </header>

        {/* ── A/B Experiment Controller & Live Switcher ────────────────── */}
        <section className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5">
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-[#1c1c1c]">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-none bg-[#161616] border border-[#333333] flex items-center justify-center text-white shrink-0">
                <span className="material-symbols-outlined text-xl">tune</span>
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-xs font-bold text-white uppercase tracking-wider">
                    A/B Testing Controller
                  </h2>
                  <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-none bg-[#15803d]/20 border border-[#22c55e]/40 text-[#22c55e] text-[10px] font-mono font-bold uppercase tracking-wider">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
                    LIVE SERVING: VARIANT {abConfig?.current_variant || 'A'}
                  </div>
                </div>
                <p className="text-xs text-[#888888] mt-1 font-mono uppercase tracking-wider">
                  Select manual variant override or set automatic switching rules for mirror sessions.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="text-[#666666] uppercase text-[10px]">CURRENT MODE:</span>
              <span className="text-white font-bold uppercase px-2 py-1 bg-[#1a1a1a] border border-[#333333] text-[11px]">
                {(abConfig?.mode || 'auto').replace('_', ' ').toUpperCase()}
              </span>
            </div>
          </div>

          {/* Controller Mode Buttons */}
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {[
              { id: 'force_a', label: 'FORCE VARIANT A', sub: 'Standard layout', icon: 'looks_one' },
              { id: 'force_b', label: 'FORCE VARIANT B', sub: 'Touchless + dwell pill', icon: 'looks_two' },
              { id: 'auto', label: 'ALTERNATE SESSIONS', sub: '50/50 per user', icon: 'sync_alt' },
              { id: 'hourly', label: 'SWITCH HOURLY', sub: 'Rotates each hour', icon: 'schedule' },
              { id: 'daily', label: 'SWITCH DAILY', sub: 'Rotates each day', icon: 'calendar_today' },
            ].map((option) => {
              const isActive = (abConfig?.mode || 'auto') === option.id
              return (
                <button
                  key={option.id}
                  onClick={() => handleSwitchABMode(option.id)}
                  disabled={savingConfig}
                  className={`p-3 text-left transition-all rounded-none cursor-pointer border ${
                    isActive
                      ? 'bg-white text-black border-white shadow-lg'
                      : 'bg-[#121212] hover:bg-[#1a1a1a] text-white border-[#262626]'
                  } disabled:opacity-50`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="material-symbols-outlined text-base">
                      {option.icon}
                    </span>
                    {isActive && (
                      <span className="text-[9px] font-bold tracking-widest uppercase bg-black text-white px-1.5 py-0.2">
                        ACTIVE
                      </span>
                    )}
                  </div>
                  <div className={`text-[11px] font-bold tracking-wider uppercase ${isActive ? 'text-black' : 'text-white'}`}>
                    {option.label}
                  </div>
                  <div className={`text-[10px] mt-0.5 ${isActive ? 'text-[#333333]' : 'text-[#777777]'}`}>
                    {option.sub}
                  </div>
                </button>
              )
            })}
          </div>

          {configFeedback && (
            <div className="mt-3 text-xs font-mono text-[#22c55e] flex items-center gap-1.5">
              <span className="material-symbols-outlined text-sm">check_circle</span>
              {configFeedback}
            </div>
          )}
        </section>

        {/* Loading / Error States */}
        {loading && !data && (
          <div className="py-20 flex flex-col items-center justify-center gap-4 text-center">
            <div className="w-8 h-8 border-2 border-white border-t-transparent animate-spin rounded-none" />
            <p className="text-xs text-[#888888] tracking-widest uppercase">Loading telemetry metrics...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-950/20 border border-red-500/30 rounded-none p-6 text-center">
            <span className="material-symbols-outlined text-red-400 text-3xl mb-2">error</span>
            <p className="text-xs text-red-300 font-mono">{error}</p>
            <button
              onClick={() => fetchAnalytics()}
              className="mt-4 px-4 py-2 rounded-none text-xs bg-white text-black font-bold uppercase cursor-pointer hover:bg-[#e0e0e0]"
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
              <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-[11px] uppercase tracking-wider font-bold">Total Sessions</span>
                  <span className="material-symbols-outlined text-lg text-white">visibility</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white font-mono">{data.total_sessions}</span>
                  <span className="text-xs text-[#666666] uppercase">visits</span>
                </div>
                <div className="mt-3 pt-3 border-t border-[#1c1c1c] flex items-center justify-between text-xs text-[#888888]">
                  <span>User: <strong className="text-white">{data.user_sessions}</strong></span>
                  <span>Guest: <strong className="text-white">{data.guest_sessions}</strong></span>
                </div>
              </div>

              {/* Avg Session Duration */}
              <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-[11px] uppercase tracking-wider font-bold">Avg Engagement</span>
                  <span className="material-symbols-outlined text-lg text-white">timer</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white font-mono">
                    {data.avg_user_duration_sec > 0 ? `${data.avg_user_duration_sec}s` : '0s'}
                  </span>
                  <span className="text-xs text-[#666666] uppercase">user avg</span>
                </div>
                <div className="mt-3 pt-3 border-t border-[#1c1c1c] flex items-center justify-between text-xs text-[#888888]">
                  <span>Guest avg:</span>
                  <strong className="text-white">{data.avg_guest_duration_sec}s</strong>
                </div>
              </div>

              {/* Auth Breakdown */}
              <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-[11px] uppercase tracking-wider font-bold">Authentication</span>
                  <span className="material-symbols-outlined text-lg text-white">badge</span>
                </div>
                <div className="flex items-baseline gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm text-[#aaaaaa]">face</span>
                    <span className="text-2xl font-bold font-mono text-white">{data.face_auth_count}</span>
                  </div>
                  <span className="text-xs text-[#555555]">/</span>
                  <div className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm text-[#aaaaaa]">barcode_scanner</span>
                    <span className="text-2xl font-bold font-mono text-white">{data.barcode_auth_count}</span>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-[#1c1c1c] flex items-center justify-between text-[11px] text-[#888888] uppercase">
                  <span>Face ID</span>
                  <span>Barcode ID</span>
                </div>
              </div>

              {/* Gesture Interactions */}
              <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5 flex flex-col justify-between">
                <div className="flex items-center justify-between text-[#888888] mb-3">
                  <span className="text-[11px] uppercase tracking-wider font-bold">Total Gestures</span>
                  <span className="material-symbols-outlined text-lg text-white">front_hand</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white font-mono">{data.total_gesture_events}</span>
                  <span className="text-xs text-[#666666] uppercase">actions logged</span>
                </div>
                <div className="mt-3 pt-3 border-t border-[#1c1c1c] flex items-center justify-between text-xs text-[#888888]">
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
            <div className="flex items-center gap-2 border-b border-[#222222] pb-3">
              {[
                { id: 'overview', label: 'A/B Battle Card' },
                { id: 'users', label: 'Users' },
                { id: 'screensaver', label: 'Screensaver' },
                { id: 'hourly', label: 'Hourly Peak Distribution' },
                { id: 'sessions', label: `Recent Session Feed (${data.recent_sessions?.length || 0})` },
                { id: 'biometrics', label: 'Biometric Audit & Collisions' },
              ].map(t => (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`px-4 py-2 rounded-none text-xs font-mono font-bold uppercase tracking-wider transition-all cursor-pointer border ${
                    activeTab === t.id
                      ? 'bg-white text-black border-white'
                      : 'bg-[#121212] text-[#888888] hover:text-white border-[#222222] hover:border-[#444444]'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* ── TAB 1: A/B TESTING DEEP-DIVE BATTLE CARD ───────────────── */}
            {activeTab === 'users' && <UsersPanel />}
            {activeTab === 'screensaver' && <ScreensaverPanel />}

            {activeTab === 'overview' && (
              <section className="flex flex-col gap-6">
                {/* Hypothesis Status Card */}
                <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
                    <div>
                      <h2 className="text-base font-bold text-white tracking-tight uppercase flex items-center gap-2">
                        <span className="material-symbols-outlined text-white">compare_arrows</span>
                        A/B Test Results: Variant A (Control) vs Variant B (Treatment)
                      </h2>
                      <p className="text-xs text-[#888888] mt-1 uppercase tracking-wider">
                        Statistical evaluation of touchless framing banner and proactive timetable return cues.
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <div className="bg-[#121212] border border-[#262626] rounded-none px-3 py-1.5 flex items-center gap-2 text-xs">
                        <span className="text-[#888888] uppercase">Gesture Lift:</span>
                        <span
                          className={`font-mono font-bold ${
                            data.adoption_rate_lift_pct >= 0 ? 'text-white' : 'text-red-400'
                          }`}
                        >
                          {data.adoption_rate_lift_pct >= 0 ? '+' : ''}
                          {data.adoption_rate_lift_pct.toFixed(1)}%
                        </span>
                      </div>

                      {data.z_score !== undefined && data.z_score !== 0 && (
                        <div className="bg-[#121212] border border-[#262626] rounded-none px-3 py-1.5 flex items-center gap-2 text-xs font-mono">
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
                        <span className="px-2.5 py-1 rounded-none bg-white text-black border border-white text-[10px] font-bold font-mono uppercase tracking-wider flex items-center gap-1">
                          ✓ Significant (p &lt; 0.05)
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-none bg-[#161616] text-[#888888] border border-[#2a2a2a] text-[10px] font-mono uppercase">
                          N = {data.total_sessions} (Sampling)
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Side-by-side Battle Card Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Variant A (Control) */}
                    <div className="bg-[#0a0a0a] border border-[#222222] rounded-none p-5 flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-4 border-b border-[#1c1c1c] pb-3">
                          <div>
                            <span className="text-[10px] uppercase font-mono font-bold tracking-widest text-[#777777]">
                              Variant A • Control
                            </span>
                            <h3 className="text-sm font-bold text-white mt-0.5 uppercase">Implicit / Standard Mirror</h3>
                          </div>
                          <span className="px-2.5 py-1 rounded-none bg-[#141414] border border-[#262626] text-xs font-mono text-[#aaaaaa]">
                            {data.variant_a.total_sessions} sessions
                          </span>
                        </div>

                        <ul className="text-xs text-[#888888] mb-5 space-y-1 list-disc list-inside">
                          <li>Tutorial video plays without touchless callout banner.</li>
                          <li>Top-right dwell cue remains hidden until hand arrives.</li>
                          <li>Vulnerable to false touchscreen tapping assumption.</li>
                        </ul>

                        <div className="space-y-3 pt-4 border-t border-[#1c1c1c]">
                          {/* Gesture Adoption Rate */}
                          <div>
                            <div className="flex justify-between text-xs mb-1">
                              <span className="text-[#888888] uppercase">Gesture Adoption Rate</span>
                              <span className="font-mono font-bold text-white">
                                {data.variant_a.gesture_adoption_rate.toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full h-2 bg-[#1a1a1a] rounded-none overflow-hidden">
                              <div
                                className="h-full bg-white/40 rounded-none"
                                style={{ width: `${Math.min(100, data.variant_a.gesture_adoption_rate)}%` }}
                              />
                            </div>
                          </div>

                          {/* Zero-Interaction (Screen-Tap Confusion) */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#1c1c1c]">
                            <span className="text-[#888888] uppercase">Zero-Interaction (Glass Tap Bounce)</span>
                            <span className="font-mono text-red-400 font-semibold">
                              {data.variant_a.zero_interaction_rate ? `${data.variant_a.zero_interaction_rate.toFixed(1)}%` : '0.0%'}
                            </span>
                          </div>

                          {/* Avg Time to First Gesture */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#1c1c1c]">
                            <span className="text-[#888888] uppercase">Avg Time to First Gesture</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_a.avg_time_to_first_gesture_sec > 0
                                ? `${data.variant_a.avg_time_to_first_gesture_sec}s`
                                : 'N/A'}
                            </span>
                          </div>

                          {/* Timetable Toggle Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#1c1c1c]">
                            <span className="text-[#888888] uppercase">Timetable Toggle Rate (Dwell)</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_a.timetable_toggle_rate.toFixed(1)}% ({data.variant_a.timetable_toggles} times)
                            </span>
                          </div>

                          {/* Dwell Success Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#1c1c1c]">
                            <span className="text-[#888888] uppercase">Dwell Completion Ratio</span>
                            <span className="font-mono text-[#cccccc] font-semibold">
                              {data.variant_a.dwell_success_rate ? `${data.variant_a.dwell_success_rate.toFixed(1)}%` : 'N/A'} ({data.variant_a.dwell_completed_count} ok / {data.variant_a.dwell_abandoned_count} aban)
                            </span>
                          </div>

                          {/* Article Read Duration */}
                          <div className="flex justify-between items-center text-xs py-1">
                            <span className="text-[#888888] uppercase">Modal Read Avg</span>
                            <span className="font-mono text-[#cccccc]">
                              {data.variant_a.avg_modal_read_sec > 0 ? `${data.variant_a.avg_modal_read_sec}s (${data.variant_a.article_modal_opens} opens)` : '0s'}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Variant B (Treatment) */}
                    <div className="bg-[#0e0e0e] border border-[#333333] rounded-none p-5 flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-4 border-b border-[#222222] pb-3">
                          <div>
                            <span className="text-[10px] uppercase font-mono font-bold tracking-widest text-white">
                              Variant B • Treatment
                            </span>
                            <h3 className="text-sm font-bold text-white mt-0.5 uppercase">Explicit Touchless Guidance</h3>
                          </div>
                          <span className="px-2.5 py-1 rounded-none bg-white text-black text-xs font-mono font-bold uppercase">
                            {data.variant_b.total_sessions} sessions
                          </span>
                        </div>

                        <ul className="text-xs text-[#aaaaaa] mb-5 space-y-1 list-disc list-inside">
                          <li>Explicit banner: &ldquo;Touchless Controls - Move hand in air&rdquo;.</li>
                          <li>Proactive top-right dwell hint pill with active % progress.</li>
                          <li>Designed to dismantle the physical glass-touch expectation.</li>
                        </ul>

                        <div className="space-y-3 pt-4 border-t border-[#222222]">
                          {/* Gesture Adoption Rate */}
                          <div>
                            <div className="flex justify-between text-xs mb-1">
                              <span className="text-[#aaaaaa] uppercase">Gesture Adoption Rate</span>
                              <span className="font-mono font-bold text-white flex items-center gap-1">
                                {data.variant_b.gesture_adoption_rate.toFixed(1)}%
                                {data.adoption_rate_lift_pct > 0 && (
                                  <span className="text-[10px] text-[#888888] font-mono">
                                    (+{data.adoption_rate_lift_pct.toFixed(0)}%)
                                  </span>
                                )}
                              </span>
                            </div>
                            <div className="w-full h-2 bg-[#1a1a1a] rounded-none overflow-hidden">
                              <div
                                className="h-full bg-white rounded-none"
                                style={{ width: `${Math.min(100, data.variant_b.gesture_adoption_rate)}%` }}
                              />
                            </div>
                          </div>

                          {/* Zero-Interaction (Screen-Tap Confusion) */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#222222]">
                            <span className="text-[#aaaaaa] uppercase">Zero-Interaction (Glass Tap Bounce)</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_b.zero_interaction_rate ? `${data.variant_b.zero_interaction_rate.toFixed(1)}%` : '0.0%'}
                              {data.variant_a.zero_interaction_rate > 0 && data.variant_b.zero_interaction_rate < data.variant_a.zero_interaction_rate && (
                                <span className="text-[10px] text-[#888888] ml-1">
                                  (-{(data.variant_a.zero_interaction_rate - data.variant_b.zero_interaction_rate).toFixed(0)}% bounce)
                                </span>
                              )}
                            </span>
                          </div>

                          {/* Avg Time to First Gesture */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#222222]">
                            <span className="text-[#aaaaaa] uppercase">Avg Time to First Gesture</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_b.avg_time_to_first_gesture_sec > 0
                                ? `${data.variant_b.avg_time_to_first_gesture_sec}s`
                                : 'N/A'}
                            </span>
                          </div>

                          {/* Timetable Toggle Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#222222]">
                            <span className="text-[#aaaaaa] uppercase">Timetable Toggle Rate (Dwell)</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_b.timetable_toggle_rate.toFixed(1)}% ({data.variant_b.timetable_toggles} times)
                            </span>
                          </div>

                          {/* Dwell Success Rate */}
                          <div className="flex justify-between items-center text-xs py-1 border-b border-[#222222]">
                            <span className="text-[#aaaaaa] uppercase">Dwell Completion Ratio</span>
                            <span className="font-mono text-white font-semibold">
                              {data.variant_b.dwell_success_rate ? `${data.variant_b.dwell_success_rate.toFixed(1)}%` : 'N/A'} ({data.variant_b.dwell_completed_count} ok / {data.variant_b.dwell_abandoned_count} aban)
                            </span>
                          </div>

                          {/* Article Read Duration */}
                          <div className="flex justify-between items-center text-xs py-1">
                            <span className="text-[#aaaaaa] uppercase">Modal Read Avg</span>
                            <span className="font-mono text-white">
                              {data.variant_b.avg_modal_read_sec > 0 ? `${data.variant_b.avg_modal_read_sec}s (${data.variant_b.article_modal_opens} opens)` : '0s'}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {/* ── TAB 2: HOURLY PEAK USAGE DISTRIBUTION ─────────────────── */}
            {activeTab === 'hourly' && (
              <section className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-base font-bold text-white tracking-tight uppercase flex items-center gap-2">
                      <span className="material-symbols-outlined text-white">schedule</span>
                      24-Hour Traffic &amp; Peak Mirror Usage
                    </h2>
                    <p className="text-xs text-[#888888] mt-1 uppercase tracking-wider">
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
                        <div className="absolute -top-10 opacity-0 group-hover:opacity-100 transition-opacity bg-[#1c1c1c] text-white border border-[#333333] px-2 py-1 rounded-none text-[10px] font-mono whitespace-nowrap pointer-events-none z-10 shadow-lg">
                          {hour}:00 - {count} session{count === 1 ? '' : 's'}
                        </div>

                        <div className="w-full flex justify-center items-end h-full">
                          <motion.div
                            initial={{ height: 0 }}
                            animate={{ height: `${heightPct}%` }}
                            transition={{ duration: 0.5, delay: hour * 0.015 }}
                            className={`w-full max-w-[28px] rounded-none transition-all ${
                              count > 0
                                ? isPeak
                                  ? 'bg-white hover:bg-[#e0e0e0]'
                                  : 'bg-[#444444] hover:bg-[#666666]'
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

                <div className="flex items-center justify-between text-xs text-[#888888] pt-4 font-mono">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 bg-white rounded-none" />
                      School Peak Intervals (8am, 10am, 12pm, 3pm)
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 bg-[#444444] rounded-none" />
                      Standard Hours
                    </span>
                  </div>
                  <span className="text-[#666666]">Data timezone: Mirror local</span>
                </div>
              </section>
            )}

            {/* ── TAB 3: RECENT SESSIONS TABLE ───────────────────────────── */}
            {activeTab === 'sessions' && (
              <section className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                  <div>
                    <h2 className="text-base font-bold text-white tracking-tight uppercase flex items-center gap-2">
                      <span className="material-symbols-outlined text-white">history</span>
                      Recent Session Activity Log
                    </h2>
                    <p className="text-xs text-[#888888] mt-1 uppercase tracking-wider">
                      Individual telemetry events collected from the mirror hardware.
                    </p>
                  </div>

                  {/* Filter Buttons */}
                  <div className="flex items-center gap-2">
                    {['ALL', 'A', 'B'].map((f) => (
                      <button
                        key={f}
                        onClick={() => setSelectedVariantFilter(f)}
                        className={`px-3.5 py-1.5 rounded-none text-xs font-mono font-bold uppercase transition-all cursor-pointer border ${
                          selectedVariantFilter === f
                            ? 'bg-white text-black border-white'
                            : 'bg-[#141414] text-[#888888] border-[#2a2a2a] hover:border-[#555555]'
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
                        <tr className="bg-[#080808] border-b border-[#222222] text-[#888888] font-mono uppercase text-[10px] tracking-wider">
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
                      <tbody className="divide-y divide-[#161616] font-mono">
                        {filteredSessions.map((s, idx) => {
                          const gestureActs = (s.gesture_scroll_count || 0) + (s.gesture_tap_count || 0) + (s.timetable_toggle_count || 0) + (s.dwell_completed_count || 0);
                          const totalActs = gestureActs > 0 ? gestureActs : (s.has_gesture ? 1 : 0);

                          return (
                            <tr key={s.session_id || idx} className="hover:bg-white/[0.03] transition-colors">
                              <td className="py-3 px-3 font-semibold text-white">
                                {s.session_id ? s.session_id.slice(-10) : `sess-${idx}`}
                              </td>
                              <td className="py-3 px-3">
                                <span
                                  className={`px-2 py-0.5 rounded-none text-[10px] font-bold uppercase border ${
                                    s.session_type === 'user'
                                      ? 'bg-[#181818] text-white border-[#333333]'
                                      : 'bg-[#101010] text-[#777777] border-[#222222]'
                                  }`}
                                >
                                  {s.session_type}
                                </span>
                              </td>
                              <td className="py-3 px-3 text-[#aaaaaa]">
                                {s.auth_method === 'face' && <span className="text-white font-bold">Face ID</span>}
                                {s.auth_method === 'barcode' && <span className="text-white font-bold">Barcode</span>}
                                {s.auth_method !== 'face' && s.auth_method !== 'barcode' && (
                                  <span className="text-[#666666]">{s.auth_method || 'Presence'}</span>
                                )}
                              </td>
                              <td className="py-3 px-3">
                                <span
                                  className={`px-2 py-0.5 rounded-none text-[10px] font-bold border ${
                                    s.variant === 'B'
                                      ? 'bg-white text-black border-white'
                                      : 'bg-[#141414] text-[#888888] border-[#333333]'
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
                                  <span className="text-white font-bold">
                                    {totalActs} acts ({s.time_to_first_gesture_sec ? `${s.time_to_first_gesture_sec}s` : '0.1s'} first)
                                  </span>
                                ) : (
                                  <span className="text-[#555555]">None (Glass Tap?)</span>
                                )}
                              </td>
                              <td className="py-3 px-3">
                                {s.timetable_toggle_count > 0 ? (
                                  <span className="text-white font-bold">✓ Toggled</span>
                                ) : s.dwell_abandoned_count > 0 ? (
                                  <span className="text-[#888888]">Abandoned ({s.dwell_abandoned_count})</span>
                                ) : (
                                  <span className="text-[#555555]">-</span>
                                )}
                              </td>
                              <td className="py-3 px-3 text-right text-[#777777] text-[11px]">
                                {s.created_at ? new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            {/* ── TAB 4: BIOMETRIC AUDIT & COLLISION LOGS ───────────────────── */}
            {activeTab === 'biometrics' && (
              <section className="space-y-6">
                {/* Overview Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-[11px] uppercase font-mono tracking-wider font-bold">Enrolled Faces</span>
                      <span className="material-symbols-outlined text-lg text-white">face</span>
                    </div>
                    <div className="text-3xl font-extrabold text-white font-mono">
                      {auditData?.total_enrolled ?? '-'}
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono uppercase">Unique student vectors stored</p>
                  </div>

                  <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-[11px] uppercase font-mono tracking-wider font-bold">Collisions Intercepted</span>
                      <span className="material-symbols-outlined text-lg text-white">security</span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-extrabold text-white font-mono">
                        {auditData?.collisions?.length || 0}
                      </span>
                      <span className="text-xs text-[#888888] uppercase">attempts</span>
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono uppercase">Duplicate registration blocks</p>
                  </div>

                  <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-[11px] uppercase font-mono tracking-wider font-bold">Distance Threshold</span>
                      <span className="material-symbols-outlined text-lg text-white">straighten</span>
                    </div>
                    <div className="text-3xl font-extrabold text-white font-mono">
                      &lt; 0.38
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono uppercase">Strict Euclidean threshold</p>
                  </div>

                  <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-5">
                    <div className="flex items-center justify-between text-[#888888] mb-2">
                      <span className="text-[11px] uppercase font-mono tracking-wider font-bold">Admin Escalation</span>
                      <span className="material-symbols-outlined text-lg text-white">mail</span>
                    </div>
                    <div className="text-xs font-bold text-white font-mono truncate" title={contactEmail}>
                      {contactEmail}
                    </div>
                    <p className="text-[11px] text-[#666666] mt-1 font-mono uppercase">Primary contact</p>
                  </div>
                </div>

                {/* Collisions Log Table */}
                <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                        <span className="material-symbols-outlined text-white text-lg">warning</span>
                        Biometric Collision &amp; Impersonation Intercept Log
                      </h3>
                      <p className="text-xs text-[#888888] mt-0.5 uppercase tracking-wider">
                        Logged whenever a student registration attempts to use a facial biometric vector that matches an existing account
                      </p>
                    </div>
                  </div>

                  {!auditData?.collisions || auditData.collisions.length === 0 ? (
                    <div className="py-12 text-center text-[#666666] font-mono text-xs border border-dashed border-[#222222] rounded-none bg-[#0a0a0a]">
                      <span className="material-symbols-outlined text-3xl text-white/40 mb-2 block">verified_user</span>
                      No biometric collisions detected yet. All registered faces are unique.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-[#080808] border-b border-[#222222] text-[#888888] font-mono uppercase text-[10px] tracking-wider">
                            <th className="py-3 px-3">Timestamp (UTC)</th>
                            <th className="py-3 px-3">Attempted Account</th>
                            <th className="py-3 px-3">Matched Existing Account</th>
                            <th className="py-3 px-3">Distance Score</th>
                            <th className="py-3 px-3">Action</th>
                            <th className="py-3 px-3 text-right">Escalation</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#161616] font-mono">
                          {auditData.collisions.map((col, idx) => (
                            <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                              <td className="py-3 px-3 text-[#aaaaaa] text-[11px]">
                                {col.timestamp ? new Date(col.timestamp).toLocaleString() : '-'}
                              </td>
                              <td className="py-3 px-3 font-semibold text-white">
                                {col.attempted_user || 'Unknown'}
                              </td>
                              <td className="py-3 px-3 text-white font-bold">
                                {col.matched_user || 'Unknown'}
                              </td>
                              <td className="py-3 px-3">
                                <span className="px-2 py-0.5 rounded-none bg-[#161616] text-white border border-[#333333] text-[10px] font-bold">
                                  {col.min_distance} (&lt; 0.38)
                                </span>
                              </td>
                              <td className="py-3 px-3">
                                <span className="px-2 py-0.5 rounded-none bg-white text-black text-[10px] font-bold uppercase">
                                  {col.action || 'BLOCKED'}
                                </span>
                              </td>
                              <td className="py-3 px-3 text-right text-[#888888] text-[11px]">
                                {col.contact_email || contactEmail}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Enrolled faces: who they are lives in the Users tab */}
                <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6 flex items-center justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <span className="material-symbols-outlined text-white text-lg">badge</span>
                      Registered Face Scans
                    </h3>
                    <p className="text-xs text-[#888888] mt-0.5 uppercase tracking-wider">
                      See and remove individual scans in the Users tab
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveTab('users')}
                    className="text-xs font-mono text-white bg-[#141414] px-3 py-1.5 rounded-none border border-[#333333] hover:border-white cursor-pointer"
                  >
                    {auditData?.total_enrolled || 0} enrolled →
                  </button>
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  )
}
