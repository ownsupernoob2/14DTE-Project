import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth0 } from '@auth0/auth0-react';
import { motion } from 'framer-motion';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

/** Format a time string "HH:MM" or ISO datetime to 12-hour "h:mma" */
function formatTime12h(dateObj, fallbackStr) {
  if (dateObj && !isNaN(dateObj.getTime())) {
    return dateObj.toLocaleTimeString('en-NZ', { hour: 'numeric', minute: '2-digit', hour12: true }).toLowerCase().replace(' ', '');
  }
  if (!fallbackStr) return '--';
  const m = String(fallbackStr).match(/(\d{1,2}):(\d{2})/);
  if (m) {
    let h = parseInt(m[1], 10);
    const min = m[2];
    const ampm = h >= 12 ? 'pm' : 'am';
    h = h % 12 || 12;
    return `${h}:${min}${ampm}`;
  }
  return fallbackStr;
}

/** Validate King's High School ICS URL */
function isValidKingsHighUrl(url) {
  if (!url) return false;
  try {
    const parsed = new URL(url.trim());
    return (
      parsed.protocol === 'https:' &&
      parsed.hostname.toLowerCase() === 'kingshigh.school.kiwi' &&
      parsed.pathname.toLowerCase().startsWith('/ics/') &&
      parsed.pathname.toLowerCase().endsWith('.ics')
    );
  } catch {
    return false;
  }
}

/** Compute real-time details for a period */
function getPeriodDetails(p, now = new Date()) {
  if (!p) return { formattedStart: '--', formattedEnd: '--', remainingMins: 0, isNow: false, isDone: false };

  const rawStart = p.startTime || p.start || p.dtstart;
  const rawEnd = p.endTime || p.end || p.dtend;

  const todayStr = now.toLocaleDateString('en-CA', { timeZone: 'Pacific/Auckland' });
  const dateStr = p.date || todayStr;

  let startDate = null;
  let endDate = null;

  if (rawStart) {
    if (String(rawStart).includes('T')) {
      startDate = new Date(rawStart);
    } else {
      const [h, m] = String(rawStart).split(':').map(Number);
      const [year, month, day] = dateStr.split('-').map(Number);
      startDate = new Date(year, month - 1, day, h, m || 0);
    }
  }

  if (rawEnd) {
    if (String(rawEnd).includes('T')) {
      endDate = new Date(rawEnd);
    } else {
      const [h, m] = String(rawEnd).split(':').map(Number);
      const [year, month, day] = dateStr.split('-').map(Number);
      endDate = new Date(year, month - 1, day, h, m || 0);
    }
  }

  const formattedStart = formatTime12h(startDate, rawStart);
  const formattedEnd = formatTime12h(endDate, rawEnd);

  const nowMs = now.getTime();
  let isDone = false;
  let isNow = false;
  let remainingMins = 0;

  if (startDate && endDate) {
    const startMs = startDate.getTime();
    const endMs = endDate.getTime();

    if (nowMs >= endMs) {
      isDone = true;
    } else if (nowMs >= startMs && nowMs < endMs) {
      isNow = true;
      remainingMins = Math.max(0, Math.ceil((endMs - nowMs) / 60000));
    } else {
      remainingMins = Math.max(0, Math.ceil((endMs - nowMs) / 60000));
    }
  } else {
    isDone = p.isDone || false;
    isNow = p.isNow || false;
  }

  return {
    startDate,
    endDate,
    formattedStart,
    formattedEnd,
    remainingMins,
    isNow,
    isDone
  };
}

export default function TimetableWidget({ widget = {}, onUpdateData, readonly = false }) {
  const navigate = useNavigate();
  const { getAccessTokenSilently } = useAuth0();

  // ── Live ticking timer ─────────────────────────────────────────────────────
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 5000);
    return () => clearInterval(timer);
  }, []);

  // ── ICS URL state ──────────────────────────────────────────────────────────
  const [icsUrl, setIcsUrl] = useState(() => localStorage.getItem('timetable_ics_url') || '');
  const [urlInput, setUrlInput] = useState('');
  const [showSetup, setShowSetup] = useState(!localStorage.getItem('timetable_ics_url'));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  // ── View mode ──────────────────────────────────────────────────────────────
  const [viewMode, setViewMode] = useState(
    () => widget.data?.viewMode || localStorage.getItem('timetable_view_mode') || 'today'
  );

  // ── Subject filter ────────────────────────────────────────────────────────
  const [subjectFilter, setSubjectFilter] = useState(() => widget.data?.subjectFilter || '');

  // Keep viewMode synced if changed from parent props
  useEffect(() => {
    if (widget.data?.viewMode && widget.data.viewMode !== viewMode) {
      setViewMode(widget.data.viewMode);
    }
    if (widget.data?.subjectFilter !== undefined) {
      setSubjectFilter(widget.data.subjectFilter);
    }
  }, [widget.data?.viewMode, widget.data?.subjectFilter]);

  // Auto-sync timetable ICS URL from server if not configured locally
  useEffect(() => {
    const fetchSavedUrl = async () => {
      if (icsUrl) return;
      try {
        const token = await getAccessTokenSilently();
        const res = await fetch(`${API_URL}/api/timetable/ics`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          if (data.ics_url) {
            localStorage.setItem('timetable_ics_url', data.ics_url);
            setIcsUrl(data.ics_url);
            setShowSetup(false);
          }
        }
      } catch { /* silent */ }
    };
    fetchSavedUrl();
  }, [icsUrl, getAccessTokenSilently]);

  // ── Timetable data ─────────────────────────────────────────────────────────
  const [periods, setPeriods] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // ── Persist view mode ──────────────────────────────────────────────────────
  const handleViewModeChange = (newMode) => {
    setViewMode(newMode);
    localStorage.setItem('timetable_view_mode', newMode);
    if (onUpdateData) {
      onUpdateData({ ...widget.data, viewMode: newMode });
    }
  };

  // ── Fetch timetable ────────────────────────────────────────────────────────
  const fetchTimetable = useCallback(async () => {
    if (!icsUrl) return;
    setLoading(true);
    setError(null);
    try {
      const today = new Date().toDateString();
      const cachedDate = localStorage.getItem('timetable_cache_date');
      const cachedData = localStorage.getItem('timetable_cache_data');
      if (cachedDate === today && cachedData) {
        const cached = JSON.parse(cachedData);
        if (cached && typeof cached === 'object' && !Array.isArray(cached)) {
          setPeriods(cached.periods || []);
          if (cached.viewMode && cached.viewMode !== viewMode) {
            setViewMode(cached.viewMode);
          }
        } else {
          setPeriods(Array.isArray(cached) ? cached : []);
        }
        setLoading(false);
        return;
      }

      const token = await getAccessTokenSilently();
      const res = await fetch(`${API_URL}/api/timetable`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load timetable (${res.status})`);
      const data = await res.json();

      const list = Array.isArray(data) ? data : (data.periods || data.events || []);
      setPeriods(list);

      if (data.viewMode && data.viewMode !== viewMode) {
        setViewMode(data.viewMode);
      }

      localStorage.setItem('timetable_cache_date', today);
      localStorage.setItem('timetable_cache_data', JSON.stringify(data));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [icsUrl, getAccessTokenSilently, viewMode]);

  useEffect(() => {
    fetchTimetable();
  }, [fetchTimetable]);

  // ── Save ICS URL ───────────────────────────────────────────────────────────
  const handleSaveUrl = async (overrideUrl) => {
    const candidate = typeof overrideUrl === 'string' ? overrideUrl : urlInput;
    const trimmed = candidate.trim();
    if (!trimmed) return;

    if (!isValidKingsHighUrl(trimmed)) {
      setSaveError("URL must be a valid King's High School calendar link (e.g. https://kingshigh.school.kiwi/ics/23239-SOKKEUXX7P0OKX50E27H4H6L.ics)");
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      const token = await getAccessTokenSilently();
      const res = await fetch(`${API_URL}/api/timetable/ics`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ics_url: trimmed }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || `Server error (${res.status})`);
      }
      localStorage.setItem('timetable_ics_url', trimmed);
      localStorage.removeItem('timetable_cache_date');
      localStorage.removeItem('timetable_cache_data');
      setIcsUrl(trimmed);
      setShowSetup(false);
      setUrlInput('');
      fetchTimetable();
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Filter visible periods ─────────────────────────────────────────────────
  const visiblePeriods = (() => {
    const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: 'Pacific/Auckland' });

    let list;
    if (viewMode === 'week') {
      list = periods;
    } else {
      const todayPeriods = periods.filter(p => p.date === todayStr || !p.date);

      if (viewMode === 'tomorrow') {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        const tomorrowStr = tomorrow.toLocaleDateString('en-CA', { timeZone: 'Pacific/Auckland' });
        list = periods.filter(p => p.date === tomorrowStr);
      } else if (viewMode === 'next') {
        const nowP = todayPeriods.find(p => p.isNow);
        if (nowP) list = [nowP];
        else {
          const next = todayPeriods.find(p => !p.isDone);
          list = next ? [next] : [];
        }
      } else if (viewMode === 'remaining') {
        list = todayPeriods.filter(p => !p.isDone);
      } else {
        list = todayPeriods;
      }
    }
    return list;
  })();

  // ─── SETUP CARD (When no URL or modifying) ───────────────────────────────────
  if (showSetup) {
    if (readonly) {
      return (
        <section className="h-full flex flex-col items-center justify-center p-8 select-none text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#0d1624] border border-[#1e2f47] flex items-center justify-center mb-4 text-[#4fc3ff] shadow-lg shadow-[#4fc3ff]/10">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
            </svg>
          </div>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-[#4fc3ff]/10 text-[#4fc3ff] border border-[#4fc3ff]/20 mb-2">
            Action Required
          </span>
          <h3 className="text-xl font-bold text-white mb-2 tracking-tight">No Timetable Configured</h3>
          <p className="text-xs text-[#8f8f8f] max-w-sm mb-6 leading-relaxed">
            Link your King's High School KAMAR .ics calendar feed to display your current period, room, and countdown timer.
          </p>
          <button
            onClick={() => navigate('/timetable')}
            className="px-6 py-2.5 bg-[#4fc3ff] hover:bg-[#38b2ee] text-black font-mono text-xs font-bold uppercase tracking-wider rounded-xl transition-all cursor-pointer shadow-lg shadow-[#4fc3ff]/10 flex items-center gap-2"
          >
            <span>Configure Calendar Link</span>
            <span>→</span>
          </button>
        </section>
      );
    }

    return (
      <div className="flex flex-col h-full bg-[#000000] text-white p-6 sm:p-8 font-sans overflow-y-auto custom-scrollbar select-none">
        <div className="max-w-3xl mx-auto w-full flex flex-col gap-6 pt-2">
          {/* Header */}
          <div className="border-b border-[#1c1c1c] pb-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-[#4fc3ff]/10 text-[#4fc3ff] border border-[#4fc3ff]/20">
                King's High School · KAMAR Timetable
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Connect Your KAMAR Timetable
            </h1>
            <p className="text-xs sm:text-sm text-[#8f8f8f] mt-1.5 leading-relaxed">
              Syncing your daily timetable automatically displays your current period, room number, teacher, and an active countdown timer on the smart mirror.
            </p>
          </div>

          {/* KAMAR Step-by-Step Instructions */}
          <div className="flex flex-col gap-3">
            <h3 className="text-xs font-mono uppercase tracking-widest text-[#888888] font-bold">
              Step-by-Step KAMAR Instructions
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                {
                  step: '01',
                  title: 'Sign In to KAMAR Portal',
                  desc: 'Visit kingshigh.school.kiwi on any phone or browser and log in with your student credentials.',
                  icon: 'login',
                },
                {
                  step: '02',
                  title: 'Go to Timetable',
                  desc: 'Click "Timetable" from the main navigation sidebar to open your weekly class schedule.',
                  icon: 'calendar_month',
                },
                {
                  step: '03',
                  title: 'Locate "Subscribe / iCal"',
                  desc: 'In the top-right corner of your timetable screen, find and click the "Subscribe / iCal Feed" icon.',
                  icon: 'rss_feed',
                },
                {
                  step: '04',
                  title: 'Copy & Paste the .ics Link',
                  desc: 'Copy the URL ending in .ics (e.g. https://kingshigh.school.kiwi/ics/...) and paste it into the input below.',
                  icon: 'content_paste',
                },
              ].map(({ step, title, desc, icon }) => (
                <div
                  key={step}
                  className="bg-[#0a0a0a] border border-[#1e2f47]/50 rounded-xl p-4 flex gap-3.5 items-start hover:border-[#4fc3ff]/40 transition-colors"
                >
                  <div className="w-8 h-8 rounded-lg bg-[#0d1624] border border-[#1e2f47] text-[#4fc3ff] font-mono text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                    {step}
                  </div>
                  <div className="flex-1">
                    <h4 className="text-sm font-bold text-white mb-1 flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-sm text-[#4fc3ff]">{icon}</span>
                      {title}
                    </h4>
                    <p className="text-xs text-[#8f8f8f] leading-relaxed">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Visual KAMAR Portal Diagram Mockup */}
          <div className="bg-gradient-to-r from-[#0d1624] via-[#0b101b] to-[#0a0a0a] border border-[#1e2f47] rounded-xl p-4">
            <div className="flex items-center justify-between mb-2 pb-2 border-b border-[#1e2f47]/60">
              <span className="text-[11px] font-mono font-bold text-[#8f8f8f] uppercase flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                KAMAR Student Portal Preview
              </span>
              <span className="text-[10px] font-mono text-[#4fc3ff]">kingshigh.school.kiwi</span>
            </div>
            <div className="bg-[#05080f] border border-[#1e2f47]/80 rounded-lg p-3 text-xs font-mono text-[#cbd5e1] flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-white font-bold">Timetable · Week A / Day 3</span>
                <span className="px-2 py-0.5 rounded bg-[#4fc3ff]/20 text-[#4fc3ff] border border-[#4fc3ff]/40 text-[10px] animate-pulse">
                  🔗 Subscribe to Calendar (iCal) ⬅️ CLICK THIS
                </span>
              </div>
              <div className="text-[11px] text-[#71859e]">
                URL Format: <code className="text-[#4fc3ff]">https://kingshigh.school.kiwi/ics/&lt;student_token&gt;.ics</code>
              </div>
            </div>
          </div>

          {/* URL Input Form */}
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-xl p-5 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-mono font-bold tracking-wider text-[#cbd5e1] uppercase flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm text-[#4fc3ff]">link</span>
                KAMAR ICS Calendar Feed Link
              </label>
              <button
                type="button"
                onClick={() => {
                  setUrlInput('https://kingshigh.school.kiwi/ics/demo-12345-kingshigh.ics');
                  setSaveError(null);
                }}
                className="text-[10px] font-mono text-[#4fc3ff] hover:text-[#7dd3fc] cursor-pointer"
              >
                Use Sample Link
              </button>
            </div>

            <input
              type="url"
              placeholder="https://kingshigh.school.kiwi/ics/12345-QWERTYUIOPASDFGHJKLZXC.ics"
              value={urlInput}
              onChange={(e) => {
                setUrlInput(e.target.value);
                setSaveError(null);
              }}
              onKeyDown={(e) => e.key === 'Enter' && handleSaveUrl()}
              className="w-full bg-[#000000] border border-[#262626] focus:border-[#4fc3ff] text-white px-3.5 py-3 text-xs font-mono rounded-lg outline-none transition-colors"
            />

            {saveError && (
              <div className="text-xs text-[#f87171] font-mono flex items-center gap-1.5 bg-red-950/40 border border-red-800/40 px-3 py-2 rounded-lg">
                <span className="material-symbols-outlined text-sm">error</span>
                {saveError}
              </div>
            )}

            <div className="flex justify-end gap-3 mt-2">
              {icsUrl && (
                <button
                  type="button"
                  onClick={() => setShowSetup(false)}
                  className="px-4 py-2 border border-[#222] text-[#8f8f8f] hover:text-white font-mono text-xs uppercase rounded-lg transition-colors cursor-pointer"
                >
                  Cancel
                </button>
              )}
              <button
                type="button"
                onClick={() => handleSaveUrl()}
                disabled={saving || !urlInput.trim()}
                className="px-5 py-2.5 bg-[#4fc3ff] hover:bg-[#38b2ee] text-black font-mono text-xs font-bold uppercase rounded-lg transition-colors disabled:opacity-50 cursor-pointer shadow-lg shadow-[#4fc3ff]/10"
              >
                {saving ? 'Syncing...' : 'Save & Sync Timetable'}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading && periods.length === 0) {
    return (
      <section className="h-full flex flex-col justify-center gap-6 p-6 select-none animate-pulse">
        <div className="h-4 w-28 bg-[#1c1c1c] rounded"></div>
        <div className="h-20 w-3/4 bg-[#222222] rounded"></div>
        <div className="flex gap-8 mt-4">
          <div className="h-10 w-24 bg-[#1c1c1c] rounded"></div>
          <div className="h-10 w-24 bg-[#1c1c1c] rounded"></div>
          <div className="h-10 w-24 bg-[#1c1c1c] rounded"></div>
        </div>
      </section>
    );
  }

  // ── READONLY / DASHBOARD CLASS HERO (Matches mirror design) ────────────────
  const processedPeriods = visiblePeriods.map(p => ({
    ...p,
    details: getPeriodDetails(p, now)
  }));

  const currentP = processedPeriods.find(p => p.details.isNow) ||
    processedPeriods.find(p => !p.details.isDone) ||
    processedPeriods[0];

  const currentSubject = currentP?.subject || currentP?.summary || 'No Active Class';
  const currentRoom = currentP?.room || currentP?.location || '--';
  const currentDetails = currentP ? currentP.details : { formattedEnd: '--', remainingMins: 0 };

  const nextP = processedPeriods.find(p => p !== currentP && !p.details.isDone);
  const nextSubject = nextP?.subject || nextP?.summary || null;
  const nextRoom = nextP?.room || nextP?.location || '--';
  const nextTime = nextP ? nextP.details.formattedStart : '--';

  if (readonly) {
    return (
      <section className="h-full flex flex-col justify-center gap-8 p-6 select-none">
        {/* CURRENT CLASS BLOCK (Matches mirror hero) */}
        <div className="flex flex-col gap-2">
          <span className="text-[14px] uppercase tracking-[2px] font-extrabold text-[#38bdf8]">
            CURRENT CLASS
          </span>
          <h1 className="text-[64px] md:text-[80px] font-extrabold text-white leading-none tracking-tight my-1">
            {currentSubject}
          </h1>

          <div className="flex gap-8 md:gap-12 mt-3">
            <div className="flex flex-col">
              <span className="text-[13px] uppercase tracking-wider font-bold text-[#94a3b8]">Room</span>
              <span className="text-[32px] font-bold text-white">{currentRoom}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[13px] uppercase tracking-wider font-bold text-[#94a3b8]">Ends</span>
              <span className="text-[32px] font-bold text-white">{currentDetails.formattedEnd}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[13px] uppercase tracking-wider font-bold text-[#94a3b8]">Left</span>
              <span className={`text-[32px] font-bold font-mono ${currentDetails.remainingMins <= 5 && currentDetails.remainingMins > 0 ? 'text-[#ff4d4d]' : 'text-white'}`}>
                {currentDetails.remainingMins > 0 ? `${currentDetails.remainingMins}m` : '--'}
              </span>
            </div>
          </div>
        </div>

        {/* NEXT CLASS BLOCK */}
        {nextSubject && (
          <div className="border-t border-[#1c1c1c] pt-5 mt-2 flex items-baseline gap-6">
            <span className="text-[13px] uppercase tracking-[2px] font-bold text-[#8f8f8f] w-16 shrink-0">
              NEXT
            </span>
            <div className="flex items-baseline gap-3">
              <span className="text-[28px] md:text-[32px] font-bold text-white">
                {nextSubject}
              </span>
              <span className="text-[16px] text-[#cbd5e1] font-mono">
                {nextRoom} {nextTime !== '--' ? `· ${nextTime}` : ''}
              </span>
            </div>
          </div>
        )}
      </section>
    );
  }

  // ── EDIT / FULL CONFIGURATION VIEW ─────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-[#000000] text-white p-6 font-sans overflow-y-auto custom-scrollbar select-none">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-[#1c1c1c] mb-6 shrink-0 gap-2">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight uppercase font-mono flex items-center gap-2">
            Timetable Feed
          </h1>
          <p className="text-xs text-[#8f8f8f] font-mono mt-1">
            King's High School calendar feed status and schedule preview.
          </p>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px] text-[#8f8f8f]">
          <span>{visiblePeriods.length} PERIODS LOADED</span>
          <span className="text-[#38bdf8]">· KINGS HIGH FEED ACTIVE</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 min-h-0">
        {/* Left Column: Calendar Details & Feed Settings */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] p-5 flex flex-col gap-3">
            <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase border-b border-[#1c1c1c] pb-2">
              ACTIVE CALENDAR FEED
            </span>
            <div className="p-3 bg-[#000000] border border-[#1c1c1c] text-xs font-mono text-[#cbd5e1] break-all">
              {icsUrl || 'None configured'}
            </div>
            <button
              onClick={() => setShowSetup(true)}
              className="mt-2 py-2 px-4 bg-[#141414] hover:bg-[#1e1e1e] border border-[#2a2a2a] text-xs font-mono font-bold text-white uppercase rounded transition-colors"
            >
              Update Feed Link
            </button>
          </div>

          <div className="bg-[#0a0a0a] border border-[#1c1c1c] p-5 flex flex-col gap-3">
            <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase border-b border-[#1c1c1c] pb-2">
              VIEW SCHEDULE RANGE
            </span>
            <div className="grid grid-cols-3 gap-2">
              {['today', 'tomorrow', 'week'].map((m) => (
                <button
                  key={m}
                  onClick={() => handleViewModeChange(m)}
                  className={`py-2 px-3 border font-mono text-xs font-bold uppercase transition-colors ${viewMode === m
                    ? 'bg-[#38bdf8] text-black border-[#38bdf8]'
                    : 'bg-[#000000] text-[#8f8f8f] border-[#1c1c1c] hover:text-white'
                    }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Mirror Hero Card Live Preview */}
        <div className="lg:col-span-7 flex flex-col bg-[#0a0a0a] border border-[#1c1c1c] p-6">
          <div className="border-b border-[#1c1c1c] pb-3 mb-4 flex items-center justify-between">
            <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase">
              MIRROR DISPLAY PREVIEW
            </span>
            <span className="text-[11px] font-mono text-[#38bdf8]">MATCHING MIRROR LAYOUT</span>
          </div>

          <div className="flex-1 bg-[#000000] border border-[#1c1c1c] p-6 rounded flex flex-col justify-center">
            <div className="flex flex-col gap-2">
              <span className="text-[13px] uppercase tracking-[2px] font-extrabold text-[#38bdf8]">
                CURRENT CLASS
              </span>
              <h2 className="text-[54px] font-extrabold text-white leading-none tracking-tight my-1">
                {currentSubject}
              </h2>

              <div className="flex gap-8 mt-3">
                <div className="flex flex-col">
                  <span className="text-xs uppercase tracking-wider font-bold text-[#94a3b8]">Room</span>
                  <span className="text-2xl font-bold text-white">{currentRoom}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-xs uppercase tracking-wider font-bold text-[#94a3b8]">Ends</span>
                  <span className="text-2xl font-bold text-white">{currentDetails.formattedEnd}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-xs uppercase tracking-wider font-bold text-[#94a3b8]">Left</span>
                  <span className="text-2xl font-bold font-mono text-white">
                    {currentDetails.remainingMins > 0 ? `${currentDetails.remainingMins}m` : '--'}
                  </span>
                </div>
              </div>
            </div>

            {nextSubject && (
              <div className="border-t border-[#1c1c1c] pt-4 mt-6 flex items-baseline gap-4">
                <span className="text-xs uppercase tracking-[2px] font-bold text-[#8f8f8f]">
                  NEXT
                </span>
                <span className="text-xl font-bold text-white">{nextSubject}</span>
                <span className="text-xs text-[#cbd5e1] font-mono">{nextRoom} · {nextTime}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
