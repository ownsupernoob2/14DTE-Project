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

export default function TimetableWidget({ widget = {}, onUpdateData }) {
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

  // Keep viewMode synced if changed from parent props
  useEffect(() => {
    if (widget.data?.viewMode && widget.data.viewMode !== viewMode) {
      setViewMode(widget.data.viewMode);
    }
  }, [widget.data?.viewMode]);

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

  // ── Filter periods by view mode ────────────────────────────────────────────
  const visiblePeriods = (() => {
    // NZ Time date YYYY-MM-DD
    const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: 'Pacific/Auckland' });

    if (viewMode === 'week') {
      return periods;
    }

    const todayPeriods = periods.filter(p => p.date === todayStr || !p.date);

    if (viewMode === 'next') {
      const now = todayPeriods.find(p => p.isNow);
      if (now) return [now];
      const next = todayPeriods.find(p => !p.isDone);
      return next ? [next] : [];
    }
    if (viewMode === 'remaining') {
      return todayPeriods.filter(p => !p.isDone);
    }
    return todayPeriods;
  })();

  // ── Setup form ─────────────────────────────────────────────────────────────
  if (showSetup) {
    return (
      <div className="widget-timetable">
        <div className="timetable-header">
          <span style={{ fontWeight: 600, fontSize: '0.9em' }}>Timetable Setup</span>
        </div>
        <div className="timetable-setup">
          <p>
            Enter your school timetable ICS/iCal URL to display your daily schedule.
            You can usually get this from your school's student portal.
          </p>
          <input
            type="url"
            placeholder="https://…/timetable.ics"
            value={urlInput}
            onChange={e => setUrlInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSaveUrl()}
            autoFocus
          />
          {saveError && (
            <div style={{ color: '#f87171', fontSize: '0.78em' }}>[Error] {saveError}</div>
          )}
          <button
            className="timetable-save-btn"
            onClick={handleSaveUrl}
            disabled={saving || !urlInput.trim()}
            style={{ opacity: saving ? 0.6 : 1 }}
          >
            {saving ? 'Saving…' : 'Save & Connect'}
          </button>
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
  return (
    <div className="widget-timetable">
      {/* Header row: mode pills + gear */}
      <div className="timetable-header">
        <div className="timetable-modes">
          {[
            { id: 'today',     label: 'Today' },
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
          className="timetable-settings-btn"
          onClick={handleClearUrl}
          title="Change ICS URL"
          style={{ fontSize: '0.7em', padding: '2px 6px', width: 'auto', height: 'auto' }}
        >
          Settings
        </button>
      </div>

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
              : 'No periods scheduled today.'}
          </div>
        ) : viewMode === 'week' ? (
          (() => {
            const groups = {};
            visiblePeriods.forEach(p => {
              const d = p.date || 'Unknown';
              if (!groups[d]) groups[d] = [];
              groups[d].push(p);
            });
            const sortedDates = Object.keys(groups).sort();
            return sortedDates.map(dStr => {
              let formattedDate = dStr;
              try {
                const [year, month, day] = dStr.split('-').map(Number);
                const dateObj = new Date(year, month - 1, day);
                formattedDate = dateObj.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
              } catch (e) {
                formattedDate = dStr;
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
        ) : (
          visiblePeriods.map((period, idx) => (
            <PeriodCard key={period.uid || period.id || idx} period={period} />
          ))
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
