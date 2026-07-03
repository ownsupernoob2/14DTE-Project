import { useEffect, useState, useCallback } from 'react';
import { useAuth0 } from '@auth0/auth0-react';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

/** Format a time string "HH:MM" or ISO datetime to "HH:MM" */
function fmtTime(t) {
  if (!t) return '';
  // If it's an ISO string, extract HH:MM
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

  // ── Main view ──────────────────────────────────────────────────────────────
  if (readonly) {
    return (
      <section className="h-full flex flex-col relative overflow-hidden w-full select-none">
        {/* Sticky Header */}
        <div className="p-4 border-b border-outline-variant/30 bg-surface-container-high/50 sticky top-0 z-10 backdrop-blur-md flex justify-between items-center select-none">
          <h3 className="font-headline-md text-xl font-semibold text-primary">Next Classes</h3>
          <span className="material-symbols-outlined text-outline text-xl" data-icon="schedule">schedule</span>
        </div>

        {/* Timeline scroll container */}
        <div 
          className="p-4 flex flex-col gap-0 overflow-y-auto custom-scrollbar flex-1 pb-[25vh] relative timetable-scroll-area"
          style={{ scrollBehavior: 'smooth' }}
        >
          {/* Vertical Timeline Line */}
          <div className="absolute left-[24px] top-[16px] bottom-[25vh] w-px bg-outline-variant/30 z-0" />

          {visiblePeriods.length === 0 ? (
            <div className="opacity-50 italic text-center p-6 text-sm text-outline z-10">
              {viewMode === 'next'
                ? 'No upcoming periods today.'
                : 'All classes finished!'}
            </div>
          ) : (
            visiblePeriods.map((period, idx) => {
              const isNow = period.isNow;
              const isDone = period.isDone;
              
              // Calculate dynamic opacity based on done/future sequence
              let opacityClass = "opacity-100";
              if (isDone) {
                opacityClass = "opacity-30";
              } else if (!isNow) {
                // If it is the first upcoming, 70% opacity; second upcoming, 50%; third+, 40%
                const upcomingIdx = visiblePeriods.filter(p => !p.isDone && !p.isNow).indexOf(period);
                if (upcomingIdx === 0) opacityClass = "opacity-70";
                else if (upcomingIdx === 1) opacityClass = "opacity-50";
                else opacityClass = "opacity-40";
              }

              const range = timeRange(period.start || period.dtstart, period.end || period.dtend);
              const subject = period.summary || period.SUMMARY || period.title || 'Period';
              const location = period.location || period.LOCATION || '';

              return (
                <motion.div 
                  key={period.uid || period.id || idx}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.05 }}
                  className={`flex items-start gap-4 py-3 relative z-10 group transition-all duration-300 ${opacityClass} hover:opacity-100`}
                >
                  {/* Timeline indicator dot */}
                  <div className="flex flex-col items-center mt-2.5">
                    {isNow ? (
                      <div className="w-4 h-4 rounded-full bg-tertiary shadow-[0_0_10px_rgba(78,222,163,0.8)] border-2 border-surface-container-low z-10 group-hover:scale-125 transition-transform" />
                    ) : (
                      <div className="w-3 h-3 rounded-full bg-outline-variant border-2 border-surface-container-low z-10 group-hover:bg-primary transition-colors" />
                    )}
                  </div>

                  {/* Class Card */}
                  <div className={`border rounded-lg p-3 flex-1 transition-all duration-300 relative overflow-hidden ${
                    isNow 
                      ? 'bg-surface-container-highest border-outline-variant/50 shadow-md border-l-4 border-l-tertiary' 
                      : 'bg-surface-container border-transparent hover:bg-surface-container-highest hover:border-l-primary border-l-4 border-l-outline-variant'
                  }`}>
                    <div className="flex justify-between items-start mb-1 gap-2">
                      <h4 className="font-headline-md text-base font-bold text-on-surface line-clamp-1">
                        {subject}
                      </h4>
                      {isNow && (
                        <span className="font-label-caps text-[10px] font-bold text-tertiary bg-tertiary/10 px-2 py-0.5 rounded shrink-0">
                          NOW
                        </span>
                      )}
                    </div>

                    {range && (
                      <div className="font-label-caps text-[10px] text-outline flex items-center gap-1.5 mb-1.5 select-none">
                        <span className="material-symbols-outlined text-[13px]">schedule</span>
                        {range}
                      </div>
                    )}

                    {location && (
                      <div className="font-body-md text-xs text-on-surface-variant flex items-center gap-1.5 select-none">
                        <span className="material-symbols-outlined text-[13px]">location_on</span>
                        {location}
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })
          )}
        </div>

        {/* Swipe Hint Overlay */}
        <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-surface-container-low via-surface-container-low/80 to-transparent p-4 flex flex-col items-center justify-end pb-8 h-[20vh] pointer-events-none z-20">
          <div className="flex flex-col items-center text-primary animate-pulse scale-110">
            <span className="material-symbols-outlined text-4xl" data-icon="swipe_right">swipe_right</span>
            <span className="font-label-caps text-[10px] mt-1 font-bold tracking-wider uppercase">Swipe right for more</span>
          </div>
        </div>
      </section>
    );
  }

  // ── EDIT MODE ────────────────────────────────────────────────────────────────
  return (
    <div className="widget-timetable">
      {/* Header row: mode pills + filter */}
      <div className="timetable-header" style={{ flexWrap: 'wrap', gap: '6px' }}>
        <div className="timetable-modes">
          {[
            { id: 'today',     label: 'Today' },
            { id: 'tomorrow',  label: 'Tomorrow' },
            { id: 'next',      label: 'Next' },
            { id: 'remaining', label: 'Left' },
            { id: 'week',      label: 'Week' },
          ].map(m => (
            <button
              key={m.id}
              className={`notices-tab${viewMode === m.id ? ' active' : ''}`}
              onClick={() => handleViewModeChange(m.id)}
              style={{ padding: '4px 10px', fontSize: '0.75em' }}
            >
              {m.label}
            </button>
          ))}
        </div>
        <button
          className={`notices-settings-btn ${showTimetableSettings ? 'active' : ''}`}
          onClick={() => setShowTimetableSettings(s => !s)}
          style={{ fontSize: '0.75em', padding: '4px 8px' }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="4" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="20" y2="12"/><line x1="12" y1="18" x2="20" y2="18"/>
          </svg>
          Filter
        </button>
        <button
          className="notices-settings-btn"
          onClick={handleClearUrl}
          title="Change ICS URL"
          style={{ fontSize: '0.75em', padding: '4px 8px' }}
        >
          ICS URL
        </button>
      </div>

      {/* Subject filter panel */}
      {showTimetableSettings && (
        <div className="timetable-filter-panel">
          <div className="notices-setting-row">
            <span className="notices-setting-label">Subject</span>
            <div className="notices-keyword-wrap" style={{ flex: 1 }}>
              <input
                type="text"
                className="notices-keyword-input"
                placeholder="Filter by subject or room (applies on mirror)..."
                value={subjectFilter}
                onChange={e => handleSubjectFilterChange(e.target.value)}
              />
              {subjectFilter && (
                <button
                  className="notices-clear-btn"
                  style={{ position: 'relative', right: 'auto', marginLeft: '4px' }}
                  onClick={() => handleSubjectFilterChange('')}
                >
                  x
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Period list */}
      <div className="timetable-scroll-area">
        {visiblePeriods.length === 0 ? (
          <div style={{
            opacity: 0.5,
            fontStyle: 'italic',
            fontSize: '0.85em',
            padding: '16px 0',
            textAlign: 'center',
          }}>
            {viewMode === 'next'
              ? 'No upcoming periods today.'
              : viewMode === 'remaining'
              ? 'All periods done for today!'
              : viewMode === 'tomorrow'
              ? 'No periods scheduled tomorrow.'
              : 'No periods scheduled today.'}
          </div>
        ) : (
          (() => {
            const groups = {};
            visiblePeriods.forEach(p => {
              const d = p.date || 'Today';
              if (!groups[d]) groups[d] = [];
              groups[d].push(p);
            });
            const sortedDates = Object.keys(groups).sort();
            return sortedDates.map(dStr => {
              let formattedDate = dStr;
              if (dStr !== 'Today') {
                try {
                  const [year, month, day] = dStr.split('-').map(Number);
                  const dateObj = new Date(year, month - 1, day);
                  formattedDate = dateObj.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
                } catch (e) {
                  formattedDate = dStr;
                }
              }
              return (
                <div key={dStr} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div className="timetable-day-header">{formattedDate}</div>
                  {groups[dStr].map((period, idx) => (
                    <PeriodCard key={period.uid || period.id || idx} period={period} />
                  ))}
                </div>
              );
            });
          })()
        )}
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

      {/* Badges area: location + in-progress */}
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexShrink: 0 }}>
        {location && (
          <span className="timetable-location">{location}</span>
        )}
        {period.isNow && (
          <span className="timetable-now-badge">IN PROGRESS</span>
        )}
      </div>
    </div>
  );
}
