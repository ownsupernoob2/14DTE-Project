import { useEffect, useState, useCallback } from 'react';
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

/** Format a time string "HH:MM" or ISO datetime to "HH:MM" */
function fmtTime(t) {
  if (!t) return '';
  const m = String(t).match(/T?(\d{2}:\d{2})/);
  if (m) return m[1];
  return t;
}

/** Build a display time range string */
function timeRange(start, end) {
  const s = fmtTime(start);
  const e = fmtTime(end);
  if (s && e) return `${s} – ${e}`;
  if (s) return s;
  return '';
}

export default function TimetableWidget({ widget = {}, onUpdateData, readonly = false }) {
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

  // ── Layout mode (Minimal vs Odometer) ──────────────────────────────────────
  const [layoutMode, setLayoutMode] = useState(
    () => widget.data?.layoutMode || localStorage.getItem('timetable_layout_mode') || 'minimal'
  );

  // ── Subject filter ────────────────────────────────────────────────────────
  const [subjectFilter, setSubjectFilter] = useState(() => widget.data?.subjectFilter || '');
  const [showTimetableSettings, setShowTimetableSettings] = useState(false);

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
      } catch (err) {
        console.error("Failed to fetch saved ICS URL:", err);
      }
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

  const handleSubjectFilterChange = (val) => {
    setSubjectFilter(val);
    if (onUpdateData) {
      onUpdateData({ ...widget.data, subjectFilter: val });
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
  }, [icsUrl, getAccessTokenSilently]);

  useEffect(() => {
    fetchTimetable();
  }, [fetchTimetable]);

  // ── Save ICS URL ───────────────────────────────────────────────────────────
  const handleSaveUrl = async () => {
    const trimmed = urlInput.trim();
    if (!trimmed) return;
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
      if (!res.ok) throw new Error(`Server error (${res.status})`);
      localStorage.setItem('timetable_ics_url', trimmed);
      // Bust the cache so we fetch fresh data
      localStorage.removeItem('timetable_cache_date');
      localStorage.removeItem('timetable_cache_data');
      setIcsUrl(trimmed);
      setShowSetup(false);
      setUrlInput('');
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Clear / reset URL ──────────────────────────────────────────────────────
  const handleClearUrl = () => {
    localStorage.removeItem('timetable_ics_url');
    localStorage.removeItem('timetable_cache_date');
    localStorage.removeItem('timetable_cache_data');
    setIcsUrl('');
    setPeriods([]);
    setError(null);
    setUrlInput('');
    setShowSetup(true);
  };

  // ── Filter visible periods by subject keyword ──────────────────────────────
  const filterPeriods = (list) => {
    if (!subjectFilter || !subjectFilter.trim()) return list;
    const kw = subjectFilter.trim().toLowerCase();
    return list.filter(p => {
      const subject = (p.summary || p.SUMMARY || p.title || p.subject || '').toLowerCase();
      const location = (p.location || p.LOCATION || '').toLowerCase();
      return subject.includes(kw) || location.includes(kw);
    });
  };

  // ── Filter periods by view mode ────────────────────────────────────────────
  const visiblePeriods = (() => {
    // NZ Time date YYYY-MM-DD
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
        const now = todayPeriods.find(p => p.isNow);
        if (now) list = [now];
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
    return filterPeriods(list);
  })();

  // Auto-scrolling effect for timetable periods in readonly mode
  useEffect(() => {
    if (!readonly || loading || error || visiblePeriods.length === 0) return;

    const startScrollTimer = setTimeout(() => {
      const container = document.querySelector('.timetable-scroll-area');
      if (!container) return;

      const scrollSpeed = 0.4; // pixels per step
      const intervalTime = 30; // ms
      const holdTime = 3000; // time to hold at top/bottom (ms)
      let holdTimer = null;
      let scrollInterval = null;

      const scroll = () => {
        if (!container) return;
        const maxScroll = container.scrollHeight - container.clientHeight;
        if (maxScroll <= 0) return;

        if (container.scrollTop >= maxScroll - 1) {
          clearInterval(scrollInterval);
          holdTimer = setTimeout(() => {
            container.scrollTo({ top: 0, behavior: 'smooth' });
            holdTimer = setTimeout(() => {
              scrollInterval = setInterval(scroll, intervalTime);
            }, holdTime);
          }, holdTime);
        } else {
          container.scrollTop += scrollSpeed;
        }
      };

      holdTimer = setTimeout(() => {
        scrollInterval = setInterval(scroll, intervalTime);
      }, holdTime);

      return () => {
        if (scrollInterval) clearInterval(scrollInterval);
        if (holdTimer) clearTimeout(holdTimer);
      };
    }, 100);

    return () => clearTimeout(startScrollTimer);
  }, [readonly, loading, error, visiblePeriods.length]);

  // ── Setup / Tutorial form ──────────────────────────────────────────────────
  if (showSetup) {
    if (readonly) {
      return (
        <div className="widget-timetable" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '8px', padding: '16px', textAlign: 'center' }}>
          <span style={{ fontSize: '1.4rem' }}>📅</span>
          <span style={{ opacity: 0.5, fontStyle: 'italic', fontSize: '0.82em' }}>No timetable configured</span>
          <span style={{ opacity: 0.4, fontSize: '0.72em' }}>Add your ICS URL in the web dashboard</span>
        </div>
      );
    }
    return (
      <div className="widget-timetable" style={{ overflowY: 'auto', height: '100%' }}>
        {/* Tutorial header */}
        <div style={{
          background: 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.1))',
          borderBottom: '1px solid rgba(99,102,241,0.2)',
          padding: '14px 16px 12px',
          display: 'flex', alignItems: 'center', gap: '10px',
        }}>
          <span style={{ fontSize: '1.3rem' }}>📅</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.92em', color: '#e2e8f0' }}>Connect Your Timetable</div>
            <div style={{ fontSize: '0.72em', color: 'rgba(148,163,184,0.7)', marginTop: '1px' }}>Follow 3 steps to set up your school schedule</div>
          </div>
        </div>

        <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Steps */}
          {[
            {
              n: '1', title: 'Open your school portal',
              desc: "Log in to Kamar, NSIS, or your school's student management system.",
              icon: '🏫',
            },
            {
              n: '2', title: 'Find your iCal / ICS link',
              desc: 'Look for "Subscribe", "Export Calendar", or "iCal" under My Timetable. Copy the URL — it ends in .ics',
              icon: '🔗',
            },
            {
              n: '3', title: 'Paste it below',
              desc: 'Your timetable will sync automatically every day.',
              icon: '✅',
            },
          ].map(({ n, title, desc, icon }) => (
            <div key={n} style={{
              display: 'flex', gap: '10px', alignItems: 'flex-start',
              background: 'rgba(99,102,241,0.06)',
              border: '1px solid rgba(99,102,241,0.14)',
              borderRadius: '10px', padding: '10px 12px',
            }}>
              <div style={{
                minWidth: 28, height: 28, borderRadius: '50%',
                background: 'rgba(99,102,241,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.72em', fontWeight: 700, color: '#818cf8',
              }}>{n}</div>
              <div>
                <div style={{ fontSize: '0.82em', fontWeight: 600, color: '#e2e8f0', marginBottom: '2px' }}>
                  {icon} {title}
                </div>
                <div style={{ fontSize: '0.72em', color: 'rgba(148,163,184,0.75)', lineHeight: 1.5 }}>{desc}</div>
              </div>
            </div>
          ))}

          {/* URL input */}
          <div style={{ marginTop: '4px' }}>
            <div style={{ fontSize: '0.72em', color: 'rgba(148,163,184,0.6)', marginBottom: '6px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Your ICS / iCal URL
            </div>
            <input
              type="url"
              placeholder="https://…/timetable.ics"
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSaveUrl()}
              autoFocus
              style={{ width: '100%', boxSizing: 'border-box', marginBottom: '8px' }}
            />
            {saveError && (
              <div style={{ color: '#f87171', fontSize: '0.75em', marginBottom: '6px' }}>⚠ {saveError}</div>
            )}
            <button
              className="timetable-save-btn"
              onClick={handleSaveUrl}
              disabled={saving || !urlInput.trim()}
              style={{ opacity: saving ? 0.6 : 1, width: '100%' }}
            >
              {saving ? 'Connecting…' : '🔗 Connect Timetable'}
            </button>
          </div>

          <div style={{ fontSize: '0.68em', color: 'rgba(148,163,184,0.4)', textAlign: 'center', lineHeight: 1.5 }}>
            Your URL is stored securely and never shared. You can change it anytime in Settings → Timetable.
          </div>
        </div>
      </div>
    );
  }


  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="widget-timetable">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', opacity: 0.7, padding: '8px' }}>
          <div className="notices-spinner" />
          <span>Loading timetable…</span>
        </div>
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="widget-timetable">
        <div style={{ color: '#f87171', padding: '8px', fontSize: '0.8em' }}>
          [Error] {error}
        </div>
        <button
          className="timetable-save-btn"
          style={{ fontSize: '0.78em', padding: '6px 12px', width: 'fit-content' }}
          onClick={fetchTimetable}
        >
          Retry
        </button>
      </div>
    );
  }

  // ── Persist layout mode ──────────────────────────────────────────────────
  const handleLayoutModeChange = (mode) => {
    setLayoutMode(mode);
    localStorage.setItem('timetable_layout_mode', mode);
    if (onUpdateData) {
      onUpdateData({ ...widget.data, layoutMode: mode });
    }
  };

  // ── Main view (Readonly / Dashboard Focus layout) ─────────────────────────
  if (readonly) {
    const processedPeriods = visiblePeriods.map(p => ({
      ...p,
      details: getPeriodDetails(p, now)
    }));

    const currentP = processedPeriods.find(p => p.details.isNow) || 
                     processedPeriods.find(p => !p.details.isDone) || 
                     processedPeriods[0];

    const currentSubject = currentP?.subject || currentP?.summary || '13DTE';
    const currentRoom = currentP?.room || currentP?.location || 'T5';
    const currentDetails = currentP ? currentP.details : { formattedEnd: '1:00pm', remainingMins: 19 };

    if (layoutMode === 'odometer') {
      const pastPeriods = processedPeriods.filter(p => p !== currentP && p.details.isDone);
      const futurePeriods = processedPeriods.filter(p => p !== currentP && !p.details.isDone);

      return (
        <section className="h-full flex flex-col justify-center gap-6 p-6 select-none overflow-hidden">
          {/* ROOM CHANGE / TARGETED NOTICE ALERT (Replaces Past Classes) */}
          <motion.div 
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-[#1a0a0a] border border-[#ff4d4d]/40 rounded-none p-3.5 flex flex-col gap-1.5 shadow-lg"
          >
            <div className="flex items-center justify-between font-mono text-[11px] font-bold tracking-wider">
              <span className="text-[#ff4d4d] uppercase flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#ff4d4d] animate-pulse"></span>
                ROOM CHANGE ALERT · YEAR 12
              </span>
              <span className="text-[#8f8f8f]">TODAY</span>
            </div>
            <div className="text-[14px] font-bold text-white leading-snug">
              13DTE Period 3 moved from <span className="line-through text-[#8f8f8f]">Lab 2</span> → <span className="text-[#4fc3ff] underline font-mono">T5</span>
            </div>
            <div className="text-[11px] text-[#8f8f8f] font-mono">
              Notice for Year 12 & 13 Students · See Mr Smith
            </div>
          </motion.div>

          {/* CURRENT CLASS (BIGGEST IN MIDDLE) */}
          <div className="flex flex-col gap-2 py-2">
            <div className="flex items-center justify-between">
              <span className="text-[13px] uppercase tracking-[0.14em] font-bold text-[#4fc3ff]">
                Current Class
              </span>
            </div>

            <h1 className="text-[72px] md:text-[96px] font-bold text-white leading-[0.95] tracking-tight my-1">
              {currentSubject}
            </h1>

            <div className="flex gap-8 md:gap-12 mt-2">
              <div className="flex flex-col">
                <span className="text-[12px] uppercase tracking-wider text-[#a0a0a0]">Room</span>
                <span className="text-[28px] font-bold text-white">{currentRoom}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[12px] uppercase tracking-wider text-[#a0a0a0]">Ends</span>
                <span className="text-[28px] font-bold text-white">{currentDetails.formattedEnd}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[12px] uppercase tracking-wider text-[#a0a0a0]">Left</span>
                <span className={`text-[28px] font-bold font-mono ${currentDetails.remainingMins <= 5 ? 'text-[#ff4d4d]' : 'text-white'}`}>
                  {currentDetails.remainingMins}m
                </span>
              </div>
            </div>
          </div>

          {/* NEXT / FUTURE CLASSES (Not greyed out, clean at bottom) */}
          <div className="border-t border-[#1c1c1c] pt-4 flex flex-col gap-2">
            <div className="text-[11px] uppercase tracking-[0.14em] font-bold text-[#8f8f8f]">
              Next / Upcoming
            </div>
            {futurePeriods.length === 0 ? (
              <div className="text-[13px] text-[#8f8f8f] italic">No upcoming classes today</div>
            ) : (
              futurePeriods.slice(0, 2).map((p, idx) => (
                <div key={p.uid || p.id || idx} className="flex justify-between items-center text-white">
                  <span className="text-[22px] md:text-[26px] font-bold text-white">
                    {p.summary || p.subject}
                  </span>
                  <span className="text-[14px] text-[#d0d0d0]">
                    {p.location || p.room || ''} {p.details.formattedStart !== '--' ? `· ${p.details.formattedStart}` : ''}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      );
    }

    // MINIMAL LAYOUT (Default)
    const nextP = processedPeriods.find(p => p !== currentP && !p.details.isDone);
    const nextSubject = nextP?.subject || nextP?.summary || '13PHY';
    const nextRoom = nextP?.room || nextP?.location || 'Lab 4';
    const nextTime = nextP ? nextP.details.formattedStart : '1:00pm';

    return (
      <section className="h-full flex flex-col justify-center gap-8 p-6 select-none">
        {/* CURRENT CLASS BLOCK */}
        <div className="flex flex-col gap-2">
          <div className="text-[14px] uppercase tracking-[0.14em] font-bold text-[#4fc3ff]">
            Current Class
          </div>
          <h1 className="text-[90px] md:text-[112px] font-bold text-white leading-[0.95] tracking-tight my-1">
            {currentSubject}
          </h1>

          <div className="flex gap-10 mt-4">
            <div className="flex flex-col">
              <span className="text-[13px] uppercase tracking-wider text-[#d0d0d0]">Room</span>
              <span className="text-[30px] font-bold text-white">{currentRoom}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[13px] uppercase tracking-wider text-[#d0d0d0]">Ends</span>
              <span className="text-[30px] font-bold text-white">{currentDetails.formattedEnd}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[13px] uppercase tracking-wider text-[#d0d0d0]">Left</span>
              <span className={`text-[30px] font-bold font-mono ${currentDetails.remainingMins <= 5 ? 'text-[#ff4d4d]' : 'text-white'}`}>
                {currentDetails.remainingMins}m
              </span>
            </div>
          </div>
        </div>

        {/* NEXT CLASS BLOCK */}
        <div className="border-t border-[#1c1c1c] pt-6 flex items-baseline gap-6">
          <span className="text-[14px] uppercase tracking-[0.14em] font-bold text-[#8f8f8f] w-20 shrink-0">
            Next
          </span>
          <div className="flex items-baseline gap-3">
            <span className="text-[36px] md:text-[40px] font-bold text-white">
              {nextSubject}
            </span>
            <span className="text-[16px] text-[#d0d0d0]">
              {nextRoom} {nextTime !== '--' ? `· ${nextTime}` : ''}
            </span>
          </div>
        </div>
      </section>
    );
  }

  // ── EDIT MODE ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-[#000000] text-white p-6 font-sans overflow-y-auto custom-scrollbar select-none">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-[#1c1c1c] mb-6 shrink-0 gap-2">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight uppercase font-mono flex items-center gap-2">
            <span className="text-[#4fc3ff]">✦</span> Timetable Configuration
          </h1>
          <p className="text-xs text-[#8f8f8f] font-mono mt-1">
            Configure calendar feed source URL, layout display modes, and schedule filtering.
          </p>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px] text-[#8f8f8f]">
          <span>{visiblePeriods.length} PERIODS LOADED</span>
          <span className="text-[#4fc3ff]">· LIVE ICS SYNC</span>
        </div>
      </div>

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 min-h-0">
        {/* Left Column: Calendar Source & Settings (5 cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Calendar Source Section */}
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-none p-4 flex flex-col gap-3">
            <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase border-b border-[#1c1c1c] pb-2">
              CALENDAR SOURCE (.ICS)
            </span>
            <div className="flex items-center gap-0">
              <input
                type="text"
                value={urlInput || icsUrl}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="https://calendar-feed-url.ics"
                className="w-full bg-[#000000] border border-[#1c1c1c] rounded-none px-3 py-2 text-xs text-white font-mono placeholder-[#555] focus:outline-none focus:border-[#4fc3ff]"
              />
              <button
                onClick={handleSaveUrl}
                disabled={saving}
                className="bg-[#4fc3ff] text-black font-mono font-bold px-4 py-2 text-xs uppercase rounded-none hover:bg-[#7dd3fc] transition-colors shrink-0"
              >
                {saving ? 'SAVING...' : 'LOAD'}
              </button>
            </div>
            <p className="text-[11px] font-mono text-[#666]">
              Paste direct iCal/ICS link from Google, Outlook, or Apple Calendar.
            </p>
          </div>

          {/* Display Mode Selector Section */}
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-none p-4 flex flex-col gap-3">
            <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase border-b border-[#1c1c1c] pb-2">
              DISPLAY LAYOUT MODE
            </span>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => handleLayoutModeChange('minimal')}
                className={`p-3 border font-mono text-xs font-bold rounded-none uppercase flex flex-col items-center justify-center gap-1 transition-colors ${
                  layoutMode === 'minimal'
                    ? 'bg-[#4fc3ff] text-black border-[#4fc3ff]'
                    : 'bg-[#000000] text-[#8f8f8f] border-[#1c1c1c] hover:text-white hover:border-[#333333]'
                }`}
              >
                <span>MINIMAL</span>
                <span className="text-[10px] opacity-80 font-normal">CLEAN LIST</span>
              </button>

              <button
                onClick={() => handleLayoutModeChange('odometer')}
                className={`p-3 border font-mono text-xs font-bold rounded-none uppercase flex flex-col items-center justify-center gap-1 transition-colors ${
                  layoutMode === 'odometer'
                    ? 'bg-[#4fc3ff] text-black border-[#4fc3ff]'
                    : 'bg-[#000000] text-[#8f8f8f] border-[#1c1c1c] hover:text-white hover:border-[#333333]'
                }`}
              >
                <span>ODOMETER</span>
                <span className="text-[10px] opacity-80 font-normal">FOCUS TIMER</span>
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Timetable Preview & List (7 cols) */}
        <div className="lg:col-span-7 flex flex-col bg-[#0a0a0a] border border-[#1c1c1c] rounded-none p-4 min-h-[350px]">
          <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2 mb-3">
            <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase">
              TIMETABLE SCHEDULE LIST
            </span>
            <div className="flex gap-1">
              {['today', 'tomorrow', 'week'].map((m) => (
                <button
                  key={m}
                  onClick={() => handleViewModeChange(m)}
                  className={`px-3 py-1 font-mono text-[10px] font-bold uppercase rounded-none border transition-colors ${
                    viewMode === m
                      ? 'bg-[#4fc3ff] text-black border-[#4fc3ff]'
                      : 'bg-[#000000] text-[#8f8f8f] border-[#1c1c1c] hover:text-white'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 bg-[#000000] border border-[#1c1c1c] rounded-none p-3 overflow-y-auto custom-scrollbar flex flex-col gap-2 min-h-[220px]">
            {visiblePeriods.length === 0 ? (
              <div className="m-auto text-center font-mono text-xs text-[#666] uppercase italic py-8">
                No scheduled classes found in current feed.
              </div>
            ) : (
              visiblePeriods.map((period, idx) => (
                <div
                  key={period.uid || period.id || idx}
                  className={`p-3 border font-mono flex items-center justify-between text-xs rounded-none transition-colors ${
                    period.isNow
                      ? 'bg-[#0a0a0a] border-l-4 border-l-[#4fc3ff] border-[#1c1c1c] text-white'
                      : 'bg-[#0a0a0a] border-[#1c1c1c] text-[#d0d0d0]'
                  }`}
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="font-bold text-white text-sm">
                      {period.summary || period.subject || 'Period'}
                    </span>
                    <span className="text-[11px] text-[#8f8f8f]">
                      {timeRange(period.start || period.dtstart, period.end || period.dtend)}
                    </span>
                  </div>
                  {period.location && (
                    <span className="bg-[#1c1c1c] border border-[#333] px-2.5 py-1 text-[11px] font-mono text-[#4fc3ff]">
                      {period.location}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Force Refresh Button */}
          <button
            onClick={() => window.location.reload()}
            className="w-full mt-3 bg-[#000000] hover:bg-[#141414] text-[#d0d0d0] border border-[#1c1c1c] font-mono font-bold py-2.5 px-4 text-xs uppercase tracking-wider rounded-none flex items-center justify-center gap-2 transition-colors"
          >
            ↻ FORCE REFRESH FEED
          </button>
        </div>
      </div>
    </div>
  );
}

function PeriodCard({ period }) {
  const classes = [
    'timetable-period-card',
    period.isNow  ? 'is-now'  : '',
    period.isDone ? 'is-done' : '',
  ].filter(Boolean).join(' ');

  const range = timeRange(period.start || period.dtstart, period.end || period.dtend);
  const subject = period.summary || period.SUMMARY || period.title || 'Period';
  const location = period.location || period.LOCATION || '';

  return (
    <div className={classes}>
      {/* Time */}
      {range && <div className="timetable-time">{range}</div>}

      {/* Subject */}
      <div className="timetable-subject">{subject}</div>

      {/* Badges area: location */}
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexShrink: 0 }}>
        {location && (
          <span className="timetable-location">{location}</span>
        )}
      </div>
    </div>
  );
}
