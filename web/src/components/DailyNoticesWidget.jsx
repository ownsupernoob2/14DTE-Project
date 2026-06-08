import { useEffect, useRef, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

// Category colour palette
const CATEGORY_COLORS = {
  'General':       { bg: 'rgba(148,163,184,0.15)', accent: '#94a3b8', text: '#cbd5e1' },
  'Sports':        { bg: 'rgba(34,197,94,0.12)',   accent: '#22c55e', text: '#86efac' },
  'Meetings':      { bg: 'rgba(139,92,246,0.12)',  accent: '#8b5cf6', text: '#c4b5fd' },
  'Academic':      { bg: 'rgba(59,130,246,0.12)',  accent: '#3b82f6', text: '#93c5fd' },
  'Careers':       { bg: 'rgba(251,191,36,0.12)',  accent: '#fbbf24', text: '#fde68a' },
  'Arts & Culture':{ bg: 'rgba(244,63,94,0.12)',   accent: '#f43f5e', text: '#fda4af' },
  'Service':       { bg: 'rgba(20,184,166,0.12)',  accent: '#14b8a6', text: '#5eead4' },
};

// Category text labels (no emojis)
const CATEGORY_LABELS = {
  'General':       'General',
  'Sports':        'Sports',
  'Meetings':      'Meetings',
  'Academic':      'Academic',
  'Careers':       'Careers',
  'Arts & Culture':'Arts & Culture',
  'Service':       'Service',
};

const ALL_CATEGORIES = ['General', 'Sports', 'Meetings', 'Academic', 'Careers', 'Arts & Culture', 'Service'];
const YEAR_TABS = ['All', '9', '10', '11', '12', '13'];

// Speed presets: px per tick (tick = 25ms)
const SPEED_PRESETS = [
  { label: 'Slow',   value: 0.25 },
  { label: 'Normal', value: 0.5  },
  { label: 'Fast',   value: 1.0  },
];

/** Extract key details (date, time, location, contact) from raw HTML */
function extractDetails(html) {
  const details = {};
  if (!html) return details;
  const text = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

  const dateMatch = text.match(/\b\d{1,2}(st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(\s+\d{4})?\b/i) ||
                    text.match(/\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b/i);
  const timeMatch = text.match(/\b\d{1,2}([:.]?\d{2})?\s*(am|pm)\b/i) ||
                    text.match(/\b\d{1,2}:\d{2}\b/);
  const roomMatch = text.match(/\b(Room|Rm|Classroom)\s+([A-Za-z0-9-]+)\b/i) ||
                    text.match(/\b(Library|Auditorium|Hall|Gymnasium|Gym|Main Field|Pool|Music Suite|Performing Arts Centre|PAC)\b/i);
  const deadlineMatch = text.match(/\b(by|before|deadline[:\s]+)\s*([A-Za-z0-9\s,]+?\d{4}|\d{1,2}\s+\w+)\b/i);

  if (dateMatch) details.date = dateMatch[0].trim();
  if (timeMatch) details.time = timeMatch[0].trim();
  if (roomMatch) details.location = roomMatch[0].trim();
  if (deadlineMatch) details.deadline = deadlineMatch[0].trim();
  return details;
}

/** Build a clean text preview from HTML */
function buildPreview(html, maxLen = 120) {
  if (!html) return '';
  const text = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  return text.length > maxLen ? text.slice(0, maxLen).trimEnd() + '…' : text;
}

export default function DailyNoticesWidget({ widget = {}, onUpdateData, readonly = false }) {
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Edit mode controls
  const [searchQuery, setSearchQuery] = useState('');
  const [yearFilter, setYearFilter] = useState(widget.data?.yearFilter || 'All');
  const [catFilters, setCatFilters] = useState(() => widget.data?.catFilters ?? ALL_CATEGORIES);
  const [keywordFilter, setKeywordFilter] = useState(() => widget.data?.keywordFilter || '');
  const [scrollSpeed, setScrollSpeed] = useState(() => widget.data?.scrollSpeed ?? 0.5);
  const [showSettings, setShowSettings] = useState(false);
  const [expandedIds, setExpandedIds] = useState(new Set());

  // Mirror auto-scroll
  const scrollRef = useRef(null);
  const scrollState = useRef({ scrollInterval: null, holdTimer: null });

  // ─── Load notices ───────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const fetchNotices = async () => {
      try {
        const today = new Date().toDateString();
        const cachedDate = localStorage.getItem('notices_date');
        const cachedData = localStorage.getItem('notices_data');
        if (cachedDate === today && cachedData) {
          if (!cancelled) { setNotices(JSON.parse(cachedData)); setLoading(false); }
          return;
        }
        const res = await fetch(`${API_URL}/api/notices`);
        if (!res.ok) throw new Error('Failed to load notices');
        const data = await res.json();
        if (!cancelled) {
          if (Array.isArray(data)) {
            setNotices(data);
            localStorage.setItem('notices_date', today);
            localStorage.setItem('notices_data', JSON.stringify(data));
          } else {
            setNotices([]);
          }
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) { setError(err.message); setLoading(false); }
      }
    };
    fetchNotices();
    return () => { cancelled = true; };
  }, []);

  // ─── Sync widget.data ────────────────────────────────────────────────────────
  useEffect(() => {
    if (widget.data?.yearFilter !== undefined) setYearFilter(widget.data.yearFilter);
    if (widget.data?.catFilters !== undefined) setCatFilters(widget.data.catFilters);
    if (widget.data?.keywordFilter !== undefined) setKeywordFilter(widget.data.keywordFilter);
    if (widget.data?.scrollSpeed !== undefined) setScrollSpeed(widget.data.scrollSpeed);
  }, [widget.data]);

  // ─── Persist settings ───────────────────────────────────────────────────────
  const saveSettings = (updates) => {
    if (onUpdateData) onUpdateData({ ...widget.data, ...updates });
  };

  // ─── Enrich notices ──────────────────────────────────────────────────────────
  const enriched = notices.map((n, idx) => {
    const id = n.id || `n-${idx}-${(n.title || '').substring(0, 8)}`;
    const category = ALL_CATEGORIES.includes(n.category) ? n.category : 'General';
    const importance = n.importance || 'normal';
    const targetYears = Array.isArray(n.targetYears) && n.targetYears.length > 0 ? n.targetYears : ['All'];
    const contact = n.contact || '';
    const title = n.title || buildPreview(n.notice, 60) || `${category} Notice`;
    const details = extractDetails(n.notice);
    return { ...n, id, category, importance, targetYears, contact, title, details };
  });

  // ─── Filter ──────────────────────────────────────────────────────────────────
  const filtered = enriched.filter(n => {
    if (yearFilter !== 'All') {
      const matchesYear = n.targetYears.includes('All') || n.targetYears.includes(yearFilter);
      if (!matchesYear) return false;
    }
    if (!catFilters.includes(n.category)) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const haystack = `${n.title} ${n.category} ${n.contact} ${(n.notice || '').replace(/<[^>]*>/g, ' ')}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    // Keyword filter — applies in both edit and mirror mode
    if (keywordFilter && keywordFilter.trim()) {
      const kw = keywordFilter.trim().toLowerCase();
      const haystack = `${n.title} ${n.category} ${n.contact} ${(n.notice || '').replace(/<[^>]*>/g, ' ')}`.toLowerCase();
      if (!haystack.includes(kw)) return false;
    }
    return true;
  });

  // Sort: urgent first
  const sorted = [...filtered].sort((a, b) => {
    if (a.importance === 'high' && b.importance !== 'high') return -1;
    if (b.importance === 'high' && a.importance !== 'high') return 1;
    return 0;
  });

  // ─── Mirror auto-scroll ──────────────────────────────────────────────────────
  useEffect(() => {
    const { current: state } = scrollState;
    const cleanup = () => {
      if (state.scrollInterval) { clearInterval(state.scrollInterval); state.scrollInterval = null; }
      if (state.holdTimer) { clearTimeout(state.holdTimer); state.holdTimer = null; }
    };

    if (!readonly || loading || error || sorted.length === 0) { cleanup(); return; }

    const SPEED = scrollSpeed;  // px per tick (persisted)
    const INTERVAL = 25;        // ms
    const HOLD_TOP = 4000;      // ms pause at top
    const HOLD_BTM = 2000;      // ms pause at bottom

    const startScroll = () => {
      cleanup();
      state.holdTimer = setTimeout(() => {
        state.scrollInterval = setInterval(() => {
          const el = scrollRef.current;
          if (!el) return;
          const max = el.scrollHeight - el.clientHeight;
          if (max <= 0) { cleanup(); return; }
          if (el.scrollTop >= max - 1) {
            cleanup();
            state.holdTimer = setTimeout(() => {
              if (scrollRef.current) scrollRef.current.scrollTop = 0;
              startScroll();
            }, HOLD_BTM);
          } else {
            el.scrollTop += SPEED;
          }
        }, INTERVAL);
      }, HOLD_TOP);
    };

    const init = setTimeout(startScroll, 300);
    return () => { clearTimeout(init); cleanup(); };
  }, [readonly, loading, error, sorted.length, scrollSpeed]);

  // ─── Helpers ─────────────────────────────────────────────────────────────────
  const toggleExpand = (id) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleCat = (cat) => {
    const next = catFilters.includes(cat)
      ? catFilters.filter(c => c !== cat)
      : [...catFilters, cat];
    setCatFilters(next);
    saveSettings({ catFilters: next });
  };

  // ─── States ──────────────────────────────────────────────────────────────────
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '16px', opacity: 0.7, height: '100%' }}>
      <div className="notices-spinner" />
      <span style={{ fontSize: '0.9em' }}>Loading notices...</span>
    </div>
  );

  if (error) return (
    <div style={{ padding: '16px', color: '#f87171', fontSize: '0.85em', lineHeight: 1.5 }}>
      <div style={{ fontWeight: 700, marginBottom: '4px' }}>Could not load notices</div>
      <div style={{ opacity: 0.7 }}>{error}</div>
    </div>
  );

  if (notices.length === 0) return (
    <div style={{ padding: '16px', opacity: 0.5, fontStyle: 'italic', fontSize: '0.85em', textAlign: 'center', paddingTop: '32px' }}>
      No notices available today.
    </div>
  );

  // ─── MIRROR MODE ─────────────────────────────────────────────────────────────
  if (readonly) {
    return (
      <div className="notices-mirror-root">
        {/* Header strip */}
        <div className="notices-mirror-header">
          <span className="notices-mirror-title">Daily Notices</span>
          <span className="notices-mirror-count">
            {sorted.length} notice{sorted.length !== 1 ? 's' : ''}
            {keywordFilter && <span className="notices-filter-pill" style={{ marginLeft: '6px' }}>"{keywordFilter}"</span>}
          </span>
        </div>

        {/* Scrolling list */}
        <div className="notices-mirror-scroll" ref={scrollRef}>
          {sorted.length === 0 ? (
            <div style={{ opacity: 0.5, fontStyle: 'italic', textAlign: 'center', padding: '24px' }}>
              No notices match your settings.
            </div>
          ) : (
            sorted.map(n => {
              const colors = CATEGORY_COLORS[n.category] || CATEGORY_COLORS['General'];
              const isUrgent = n.importance === 'high';
              return (
                <div
                  key={n.id}
                  className={`notices-mirror-card ${isUrgent ? 'urgent' : ''}`}
                  style={{ borderLeftColor: isUrgent ? '#ef4444' : colors.accent }}
                >
                  {/* Top row: category + year badges */}
                  <div className="notices-mirror-card-top">
                    <span className="notices-mirror-badge" style={{ background: colors.bg, color: colors.text }}>
                      {n.category}
                    </span>
                    {isUrgent && <span className="notices-mirror-urgent-badge">URGENT</span>}
                    <div style={{ flex: 1 }} />
                    {n.targetYears.map(yr => (
                      <span key={yr} className="notices-mirror-year-badge">Y{yr}</span>
                    ))}
                  </div>

                  {/* Title */}
                  <div className="notices-mirror-card-title">{n.title}</div>

                  {/* Key details chips (date, time, location) */}
                  {(n.details.date || n.details.time || n.details.location) && (
                    <div className="notices-mirror-details">
                      {n.details.date     && <span className="notices-detail-chip">Date: {n.details.date}</span>}
                      {n.details.time     && <span className="notices-detail-chip">Time: {n.details.time}</span>}
                      {n.details.location && <span className="notices-detail-chip">Where: {n.details.location}</span>}
                    </div>
                  )}

                  {/* Body text */}
                  <div
                    className="notices-mirror-card-body"
                    dangerouslySetInnerHTML={{ __html: n.notice }}
                  />

                  {/* Contact */}
                  {n.contact && (
                    <div className="notices-mirror-contact">Contact: {n.contact}</div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    );
  }

  // ─── EDIT MODE ────────────────────────────────────────────────────────────────
  return (
    <div className="notices-edit-root">
      {/* Search + Settings toggle */}
      <div className="notices-edit-topbar">
        <div className="notices-edit-search-wrap">
          <svg className="notices-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <input
            type="text"
            placeholder="Search notices..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="notices-edit-search"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="notices-clear-btn" title="Clear">x</button>
          )}
        </div>
        <button
          className={`notices-settings-btn ${showSettings ? 'active' : ''}`}
          onClick={() => setShowSettings(s => !s)}
          title="Filter settings"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="4" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="20" y2="12"/><line x1="12" y1="18" x2="20" y2="18"/>
          </svg>
          Filters
        </button>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="notices-settings-panel">
          {/* Year tabs */}
          <div className="notices-setting-row">
            <span className="notices-setting-label">Year</span>
            <div className="notices-year-tabs">
              {YEAR_TABS.map(yr => (
                <button
                  key={yr}
                  className={`notices-year-tab ${yearFilter === yr ? 'active' : ''}`}
                  onClick={() => { setYearFilter(yr); saveSettings({ yearFilter: yr }); }}
                >
                  {yr === 'All' ? 'All' : `Y${yr}`}
                </button>
              ))}
            </div>
          </div>

          {/* Category toggles */}
          <div className="notices-setting-row" style={{ alignItems: 'flex-start' }}>
            <span className="notices-setting-label" style={{ paddingTop: '4px' }}>Categories</span>
            <div className="notices-cat-toggles">
              {ALL_CATEGORIES.map(cat => {
                const colors = CATEGORY_COLORS[cat] || CATEGORY_COLORS['General'];
                const active = catFilters.includes(cat);
                return (
                  <button
                    key={cat}
                    className={`notices-cat-chip ${active ? 'active' : ''}`}
                    style={active ? { background: colors.bg, borderColor: colors.accent, color: colors.text } : {}}
                    onClick={() => toggleCat(cat)}
                  >
                    {CATEGORY_LABELS[cat]}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Keyword filter — applies on mirror */}
          <div className="notices-setting-row">
            <span className="notices-setting-label">Keyword</span>
            <div className="notices-keyword-wrap">
              <input
                type="text"
                className="notices-keyword-input"
                placeholder="Filter by word (applies on mirror)..."
                value={keywordFilter}
                onChange={e => {
                  setKeywordFilter(e.target.value);
                  saveSettings({ keywordFilter: e.target.value });
                }}
              />
              {keywordFilter && (
                <button
                  className="notices-clear-btn"
                  style={{ position: 'relative', right: 'auto', marginLeft: '4px' }}
                  onClick={() => { setKeywordFilter(''); saveSettings({ keywordFilter: '' }); }}
                >
                  x
                </button>
              )}
            </div>
          </div>

          {/* Scroll speed — mirror only */}
          <div className="notices-setting-row">
            <span className="notices-setting-label">Speed</span>
            <div className="notices-speed-control">
              {SPEED_PRESETS.map(p => (
                <button
                  key={p.label}
                  className={`notices-speed-btn ${scrollSpeed === p.value ? 'active' : ''}`}
                  onClick={() => { setScrollSpeed(p.value); saveSettings({ scrollSpeed: p.value }); }}
                >
                  {p.label}
                </button>
              ))}
              <div className="notices-speed-slider-wrap">
                <span className="notices-speed-label">Custom:</span>
                <input
                  type="range"
                  min="0.1"
                  max="2.5"
                  step="0.05"
                  value={scrollSpeed}
                  className="notices-speed-slider"
                  onChange={e => {
                    const v = parseFloat(e.target.value);
                    setScrollSpeed(v);
                    saveSettings({ scrollSpeed: v });
                  }}
                />
                <span className="notices-speed-value">{scrollSpeed.toFixed(2)}x</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Result count */}
      <div className="notices-edit-count">
        {sorted.length} of {enriched.length} notices
        {yearFilter !== 'All' && <span className="notices-filter-pill">Year {yearFilter}</span>}
        {searchQuery && <span className="notices-filter-pill">"{searchQuery}"</span>}
        {keywordFilter && <span className="notices-filter-pill">kw: "{keywordFilter}"</span>}
      </div>

      {/* Notice list */}
      <div className="notices-edit-list">
        {sorted.length === 0 ? (
          <div style={{ opacity: 0.5, fontStyle: 'italic', textAlign: 'center', padding: '24px', fontSize: '0.85em' }}>
            No notices match your filters.
          </div>
        ) : (
          sorted.map(n => {
            const colors = CATEGORY_COLORS[n.category] || CATEGORY_COLORS['General'];
            const isUrgent = n.importance === 'high';
            const isExpanded = expandedIds.has(n.id);
            const preview = buildPreview(n.notice, 110);
            const hasMore = (n.notice || '').replace(/<[^>]*>/g, ' ').trim().length > 110;

            return (
              <div
                key={n.id}
                className={`notices-edit-card ${isUrgent ? 'urgent' : ''}`}
                style={{ borderLeftColor: isUrgent ? '#ef4444' : colors.accent }}
              >
                {/* Card header */}
                <div className="notices-edit-card-header">
                  <div className="notices-edit-badges">
                    <span className="notices-edit-badge-cat" style={{ background: colors.bg, color: colors.text }}>
                      {n.category}
                    </span>
                    {isUrgent && <span className="notices-edit-badge-urgent">URGENT</span>}
                    {n.targetYears.map(yr => (
                      <span key={yr} className="notices-edit-badge-year">Y{yr}</span>
                    ))}
                  </div>
                  {n.contact && (
                    <span className="notices-edit-contact">{n.contact}</span>
                  )}
                </div>

                {/* Title */}
                <div className="notices-edit-card-title">{n.title}</div>

                {/* Detail chips */}
                {(n.details.date || n.details.time || n.details.location || n.details.deadline) && (
                  <div className="notices-edit-details">
                    {n.details.date     && <span className="notices-detail-chip">Date: {n.details.date}</span>}
                    {n.details.time     && <span className="notices-detail-chip">Time: {n.details.time}</span>}
                    {n.details.location && <span className="notices-detail-chip">Where: {n.details.location}</span>}
                    {n.details.deadline && <span className="notices-detail-chip deadline">Deadline: {n.details.deadline}</span>}
                  </div>
                )}

                {/* Body / expand */}
                {isExpanded ? (
                  <div
                    className="notices-edit-card-body expanded"
                    dangerouslySetInnerHTML={{ __html: n.notice }}
                  />
                ) : (
                  <div className="notices-edit-card-preview">{preview}</div>
                )}

                {/* Expand toggle */}
                {hasMore && (
                  <button
                    className="notices-expand-btn"
                    onClick={() => toggleExpand(n.id)}
                  >
                    {isExpanded ? 'Show less' : 'Read more'}
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}