import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

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

/** Reusable notice card for mirror mode */
function NoticeCard({ n, urgent = false }) {
  const colors = CATEGORY_COLORS[n.category] || CATEGORY_COLORS['General'];
  const isUrgent = urgent || n.importance === 'high';
  
  // Clean notice preview text to avoid HTML tags in preview
  const previewText = buildPreview(n.notice, 120);

  return (
    <motion.article 
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      style={{ borderLeftColor: isUrgent ? '#ffb4ab' : colors.accent }}
      className="bg-surface-container rounded-lg p-4 border-l-4 relative shadow-sm hover:bg-surface-container-highest transition-colors cursor-pointer group"
    >
      <div className="flex gap-2 mb-2 flex-wrap">
        <span 
          style={{ background: colors.bg, color: colors.text }}
          className="px-2 py-0.5 rounded-full font-label-caps text-[10px] font-bold uppercase tracking-wider"
        >
          {n.category}
        </span>
        {isUrgent && (
          <span className="bg-error text-on-error px-2 py-0.5 rounded-full font-label-caps text-[10px] font-bold animate-pulse">
            URGENT
          </span>
        )}
        <div className="flex-1" />
        {n.targetYears && n.targetYears.map(yr => (
          <span key={yr} className="bg-surface-dim text-outline px-1.5 py-0.5 rounded font-label-caps text-[9px]">
            Y{yr}
          </span>
        ))}
      </div>
      
      <h4 className="font-headline-md text-[17px] font-semibold leading-snug mb-2 group-hover:text-primary transition-colors text-white">
        {n.title}
      </h4>

      {n.details && (n.details.date || n.details.time || n.details.location) && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {n.details.date && (
            <div className="font-label-caps text-[10px] text-outline bg-surface-dim inline-block px-2 py-0.5 rounded">
              Date: {n.details.date}
            </div>
          )}
          {n.details.time && (
            <div className="font-label-caps text-[10px] text-outline bg-surface-dim inline-block px-2 py-0.5 rounded">
              Time: {n.details.time}
            </div>
          )}
          {n.details.location && (
            <div className="font-label-caps text-[10px] text-outline bg-surface-dim inline-block px-2 py-0.5 rounded">
              Where: {n.details.location}
            </div>
          )}
        </div>
      )}

      <p className="font-body-md text-xs text-on-surface-variant line-clamp-3 mb-3 leading-relaxed">
        {previewText}
      </p>

      {n.contact && (
        <div className="font-label-caps text-[10px] text-outline-variant flex items-center gap-1 select-none">
          <span className="material-symbols-outlined text-[13px]">person</span>
          Contact: {n.contact}
        </div>
      )}
    </motion.article>
  );
}

export default function DailyNoticesWidget({ widget = {}, onUpdateData, readonly = false }) {
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fetchedAt, setFetchedAt] = useState(null);
  const [isWide, setIsWide] = useState(false);
  const containerRef = useRef(null);

  // Edit mode controls
  const [searchQuery, setSearchQuery] = useState('');
  const [yearFilter, setYearFilter] = useState(widget.data?.yearFilter || 'All');
  const [catFilters, setCatFilters] = useState(() => widget.data?.catFilters ?? ALL_CATEGORIES);
  const [keywordFilter, setKeywordFilter] = useState(() => widget.data?.keywordFilter || '');
  const [scrollSpeed, setScrollSpeed] = useState(() => widget.data?.scrollSpeed ?? 0.5);
  const [showSettings, setShowSettings] = useState(false);
  const [expandedIds, setExpandedIds] = useState(new Set());

  // Mirror auto-scroll (for edit mode)
  const scrollRef = useRef(null);
  const scrollState = useRef({ scrollInterval: null, holdTimer: null });

  // Mirror paginated mode state (for readonly/dashboard mode)
  const [mirrorPage, setMirrorPage] = useState(0);

  // ─── ResizeObserver: detect wide layout for 2-col ────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setIsWide(entry.contentRect.width >= 560);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ─── Load notices ───────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const fetchNotices = async () => {
      try {
        const today = new Date().toDateString();
        const cachedDate = localStorage.getItem('notices_date');
        const cachedData = localStorage.getItem('notices_data');
        const cachedFetchedAt = localStorage.getItem('notices_fetchedAt');
        if (cachedDate === today && cachedData) {
          if (!cancelled) {
            setNotices(JSON.parse(cachedData));
            setFetchedAt(cachedFetchedAt || null);
            setLoading(false);
          }
          return;
        }
        const res = await fetch(`${API_URL}/api/notices`);
        if (!res.ok) throw new Error('Failed to load notices');
        const data = await res.json();
        if (!cancelled) {
          // Handle both {fetchedAt, notices:[]} wrapper and legacy bare array
          const noticeList = Array.isArray(data) ? data : (data.notices || []);
          const fetchedAtVal = data.fetchedAt || null;
          if (noticeList.length >= 0) {
            setNotices(noticeList);
            setFetchedAt(fetchedAtVal);
            localStorage.setItem('notices_date', today);
            localStorage.setItem('notices_data', JSON.stringify(noticeList));
            if (fetchedAtVal) localStorage.setItem('notices_fetchedAt', fetchedAtVal);
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

  // ─── Mirror page auto-advance (paginated mode) ────────────────────────────────
  useEffect(() => {
    if (!readonly || sorted.length === 0) return;
    const id = setInterval(() => {
      setMirrorPage(p => (p + 1) % sorted.length);
    }, 8000);
    return () => clearInterval(id);
  }, [readonly, sorted.length]);

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

  // ─── Helper: format fetchedAt for display ───────────────────────────────────
  const formatFetchedAt = (iso) => {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleString('en-NZ', {
        weekday: 'short', day: 'numeric', month: 'short',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return null; }
  };
  const fetchedAtLabel = formatFetchedAt(fetchedAt);

  // ─── MIRROR / READONLY MODE ───────────────────────────────────────────────
  // Paginated: one notice visible at a time with dot indicator + gesture hint
  if (readonly) {
    const current = sorted[mirrorPage] || null;
    const colors = current ? (CATEGORY_COLORS[current.category] || CATEGORY_COLORS['General']) : CATEGORY_COLORS['General'];
    const isUrgent = current?.importance === 'high';
    const accent = isUrgent ? '#ef4444' : colors.accent;

    return (
      <section
        className="h-full flex flex-col select-none"
        ref={containerRef}
        style={{ fontFamily: "'Hanken Grotesk', sans-serif" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <h3 style={{
            fontSize: '20px',
            fontWeight: 700,
            color: '#a5b4fc',
            letterSpacing: '0.3px',
            fontFamily: "'Hanken Grotesk', sans-serif",
          }}>Notices</h3>
          {fetchedAtLabel && (
            <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.25)' }}>
              Updated: {fetchedAtLabel}
            </span>
          )}
          {sorted.length > 0 && (
            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.25)' }}>
              {mirrorPage + 1} / {sorted.length}
            </span>
          )}
        </div>

        {/* Thin divider */}
        <div style={{ height: '1px', background: 'rgba(255,255,255,0.07)', margin: '0' }} />

        {/* Single notice card */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {sorted.length === 0 ? (
            <div style={{ padding: '32px 20px', opacity: 0.5, textAlign: 'center', fontSize: '14px' }}>
              No notices available today.
            </div>
          ) : current ? (
            <motion.div
              key={mirrorPage}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.35 }}
              style={{
                padding: '18px 18px 14px',
                borderLeft: `3px solid ${accent}`,
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                overflow: 'hidden',
              }}
            >
              {/* Badge row */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                <span style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  color: colors.text,
                  background: colors.bg,
                  borderRadius: '6px',
                  padding: '3px 10px',
                }}>
                  {current.category}
                </span>
                {isUrgent && (
                  <span style={{
                    fontSize: '11px',
                    fontWeight: 700,
                    color: '#f87171',
                    background: 'rgba(239,68,68,0.18)',
                    borderRadius: '6px',
                    padding: '3px 10px',
                  }}>
                    URGENT
                  </span>
                )}
              </div>

              {/* Title */}
              <div style={{
                fontSize: '20px',
                fontWeight: 700,
                color: '#f8fafc',
                lineHeight: 1.3,
                wordBreak: 'break-word',
              }}>
                {current.title}
              </div>

              {/* Detail chips */}
              {(current.details?.date || current.details?.location) && (
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  {current.details?.date && (
                    <span style={{ fontSize: '11px', fontWeight: 600, color: '#c084fc' }}>
                      Date: {current.details.date}
                    </span>
                  )}
                  {current.details?.location && (
                    <span style={{ fontSize: '11px', fontWeight: 600, color: '#c084fc' }}>
                      Where: {current.details.location}
                    </span>
                  )}
                </div>
              )}

              {/* Body text */}
              <p style={{
                fontSize: '13px',
                color: '#94a3b8',
                lineHeight: 1.55,
                overflow: 'hidden',
                display: '-webkit-box',
                WebkitLineClamp: 5,
                WebkitBoxOrient: 'vertical',
              }}>
                {buildPreview(current.notice, 320)}
              </p>

              {/* Contact */}
              {current.contact && (
                <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                  ✦ Contact: {current.contact}
                </div>
              )}
            </motion.div>
          ) : null}
        </div>

        {/* Dot indicator */}
        {sorted.length > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '6px', padding: '6px 16px 4px' }}>
            {sorted.slice(0, 7).map((_, i) => (
              <div
                key={i}
                onClick={() => setMirrorPage(i)}
                style={{
                  width: i === mirrorPage ? '20px' : '6px',
                  height: '6px',
                  borderRadius: '3px',
                  background: i === mirrorPage ? 'rgba(165,180,252,0.85)' : 'rgba(255,255,255,0.2)',
                  cursor: 'pointer',
                  transition: 'width 0.3s ease, background 0.3s ease',
                }}
              />
            ))}
          </div>
        )}

        {/* Gesture footer */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '8px 16px 18px',
          gap: '4px',
        }}>
          {/* GIF placeholder — replace src with actual GIF path */}
          {/* <img src="/assets/gesture_left.gif" alt="" style={{ height: '80px' }} /> */}
          <span className="material-symbols-outlined animate-pulse"
            style={{ fontSize: '48px', color: 'rgba(165,180,252,0.55)' }}
            data-icon="swipe_left"
          >swipe_left</span>
          <span style={{
            fontSize: '12px',
            fontWeight: 600,
            color: 'rgba(148,163,184,0.65)',
            letterSpacing: '1px',
          }}>Swipe left for more</span>
        </div>
      </section>
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

      {/* Result count + last updated */}
      <div className="notices-edit-count">
        {sorted.length} of {enriched.length} notices
        {yearFilter !== 'All' && <span className="notices-filter-pill">Year {yearFilter}</span>}
        {searchQuery && <span className="notices-filter-pill">"{searchQuery}"</span>}
        {keywordFilter && <span className="notices-filter-pill">kw: "{keywordFilter}"</span>}
      </div>
      {fetchedAtLabel && (
        <div className="notices-fetched-at" style={{ marginBottom: '4px' }}>Updated: {fetchedAtLabel}</div>
      )}

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