import { useEffect, useRef, useState } from 'react';
import { motion, Reorder } from 'framer-motion';

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

/** Reusable notice card matching new-style.html */
function NoticeCard({ n, urgent = false }) {
  const isUrgent = urgent || n.importance === 'high';
  const cat = n.category || 'General';
  const isMedium = ['Academic', 'Sports', 'Arts & Culture', 'Careers', 'Meetings'].includes(cat);

  let borderClass = 'border-l-[#3a3a3a]';
  let metaColor = '#8f8f8f';
  if (isUrgent) {
    borderClass = 'border-l-[#ff4d4d]';
    metaColor = '#ff4d4d';
  } else if (isMedium) {
    borderClass = 'border-l-[#ffb020]';
    metaColor = '#ffb020';
  }

  const previewText = buildPreview(n.notice, 140);
  const dateStr = n.details?.date ? ` · ${n.details.date}` : ' · Today';

  return (
    <motion.article 
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`bg-[#0a0a0a] rounded-r p-4 border-l-[4px] ${borderClass} flex flex-col gap-1.5 shadow-sm hover:bg-[#141414] transition-colors cursor-pointer group`}
    >
      <div className="text-[12px] font-semibold tracking-wider uppercase font-mono flex items-center gap-1.5" style={{ color: metaColor }}>
        <span>{isUrgent ? `URGENT${dateStr}` : `${cat.toUpperCase()}${dateStr}`}</span>
      </div>
      
      <h4 className="text-[19px] font-bold text-white leading-tight group-hover:text-[#4fc3ff] transition-colors">
        {n.title}
      </h4>

      <p className="text-[15px] text-[#d0d0d0] leading-relaxed line-clamp-3">
        {previewText}
      </p>

      {n.contact && (
        <div className="text-[11px] text-[#8f8f8f] font-mono mt-1">
          See {n.contact}
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
  
  const getCachedConfig = () => {
    try {
      const saved = localStorage.getItem('notices_widget_config');
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  };
  const cachedConfig = getCachedConfig();

  // Edit mode controls
  const [searchQuery, setSearchQuery] = useState('');
  const [yearFilter, setYearFilter] = useState(() => widget.data?.yearFilter || cachedConfig.yearFilter || 'All');
  const [catFilters, setCatFilters] = useState(() => widget.data?.catFilters ?? cachedConfig.catFilters ?? ALL_CATEGORIES);
  const [catOrder, setCatOrder] = useState(() => widget.data?.catOrder ?? cachedConfig.catOrder ?? ALL_CATEGORIES);
  const [keywords, setKeywords] = useState(() => {
    const kf = widget.data?.keywordFilter ?? cachedConfig.keywordFilter;
    if (Array.isArray(kf)) return kf;
    if (typeof kf === 'string' && kf.trim()) return kf.split(',').map(k => k.trim()).filter(Boolean);
    return [];
  });
  const [keywordInput, setKeywordInput] = useState('');
  const [className, setClassName] = useState(() => widget.data?.className || cachedConfig.className || '');
  const [scrollSpeed, setScrollSpeed] = useState(() => widget.data?.scrollSpeed ?? cachedConfig.scrollSpeed ?? 0.5);
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

  // ─── Fetch remote config from server on load ─────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const fetchConfig = async () => {
      try {
        const res = await fetch(`${API_URL}/api/notices/config`);
        if (res.ok) {
          const cfg = await res.json();
          if (!cancelled && cfg) {
            if (cfg.yearFilter) setYearFilter(cfg.yearFilter);
            if (cfg.catFilters) setCatFilters(cfg.catFilters);
            if (cfg.catOrder) setCatOrder(cfg.catOrder);
            if (cfg.keywordFilter) {
              const kf = cfg.keywordFilter;
              if (Array.isArray(kf)) setKeywords(kf);
              else if (typeof kf === 'string' && kf.trim()) setKeywords(kf.split(',').map(k => k.trim()).filter(Boolean));
            }
            if (cfg.scrollSpeed !== undefined) setScrollSpeed(cfg.scrollSpeed);
            try { localStorage.setItem('notices_widget_config', JSON.stringify(cfg)); } catch {}
          }
        }
      } catch { /* fallback to local storage */ }
    };
    fetchConfig();
    return () => { cancelled = true; };
  }, []);

  // ─── Sync widget.data ────────────────────────────────────────────────────────
  useEffect(() => {
    if (widget.data?.yearFilter !== undefined) setYearFilter(widget.data.yearFilter);
    if (widget.data?.catFilters !== undefined) setCatFilters(widget.data.catFilters);
    if (widget.data?.catOrder !== undefined) setCatOrder(widget.data.catOrder);
    if (widget.data?.keywordFilter !== undefined) {
      const kf = widget.data.keywordFilter;
      if (Array.isArray(kf)) setKeywords(kf);
      else if (typeof kf === 'string' && kf.trim()) setKeywords(kf.split(',').map(k => k.trim()).filter(Boolean));
      else setKeywords([]);
    }
    if (widget.data?.className !== undefined) setClassName(widget.data.className);
    if (widget.data?.scrollSpeed !== undefined) setScrollSpeed(widget.data.scrollSpeed);
  }, [widget.data]);

  // ─── Persist settings (local storage + server API) ───────────────────────────
  const saveSettings = (updates) => {
    try {
      const current = getCachedConfig();
      const next = { ...current, ...updates };
      localStorage.setItem('notices_widget_config', JSON.stringify(next));

      // Push to backend server
      const payload = {
        yearFilter: next.yearFilter ?? yearFilter,
        className: next.className ?? className,
        catFilters: next.catFilters ?? catFilters,
        catOrder: next.catOrder ?? catOrder,
        keywordFilter: next.keywordFilter ?? next.keywords ?? keywords,
        scrollSpeed: next.scrollSpeed ?? scrollSpeed,
      };
      fetch(`${API_URL}/api/notices/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch(() => {});
    } catch { /* silent */ }
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
    return true;
  });

  // Sort: urgent first, then keyword-boosted matches float up, then category order
  const keywordTerms = keywords.map(k => k.toLowerCase());

  const getKeywordScore = (n) => {
    if (keywordTerms.length === 0) return 0;
    const haystack = `${n.title} ${n.category} ${n.contact} ${(n.notice || '').replace(/<[^>]*>/g, ' ')}`.toLowerCase();
    return keywordTerms.filter(kw => haystack.includes(kw)).length;
  };

  const getCatOrderScore = (n) => {
    const idx = catOrder.indexOf(n.category);
    return idx === -1 ? catOrder.length : idx;
  };

  const sorted = [...filtered].sort((a, b) => {
    // 1. Urgent notices first
    if (a.importance === 'high' && b.importance !== 'high') return -1;
    if (b.importance === 'high' && a.importance !== 'high') return 1;
    // 2. Keyword matches float to top (more matches = higher)
    const scoreA = getKeywordScore(a);
    const scoreB = getKeywordScore(b);
    if (scoreB !== scoreA) return scoreB - scoreA;
    // 3. Category order from drag list
    return getCatOrderScore(a) - getCatOrderScore(b);
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
  if (readonly) {
    return (
      <section className="h-full flex flex-col p-5 border-r border-[#1c1c1c] select-none min-h-0">
        {/* Header */}
        <div className="flex items-baseline justify-between mb-4 pb-2 border-b border-[#1c1c1c]">
          <div className="flex items-baseline gap-3">
            <h2 className="text-[22px] font-bold text-white tracking-wide">Notices</h2>
            {fetchedAtLabel && (
              <span className="text-[11px] text-[#8f8f8f] font-mono">Updated {fetchedAtLabel}</span>
            )}
          </div>
          <span className="text-[13px] text-[#d0d0d0] font-mono">{sorted.length} today</span>
        </div>

        {/* Notice list with auto-scroll */}
        <div ref={scrollRef} className="flex-1 flex flex-col gap-3 overflow-y-auto custom-scrollbar min-h-0 pr-1">
          {sorted.length === 0 ? (
            <div className="py-8 text-center text-[#8f8f8f] text-sm italic">
              No notices available today.
            </div>
          ) : (
            sorted.map((n, idx) => (
              <NoticeCard key={n.id || idx} n={n} urgent={n.importance === 'high'} />
            ))
          )}
        </div>
      </section>
    );
  }

  // ─── EDIT MODE ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-[#000000] text-white p-6 font-sans overflow-y-auto custom-scrollbar select-none">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-[#1c1c1c] mb-6 shrink-0 gap-2">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight uppercase font-mono flex items-center gap-2">
            <span className="text-[#4fc3ff]">✦</span> Notices &amp; Alerts
          </h1>
          <p className="text-xs text-[#8f8f8f] font-mono mt-1">
            Configure visual flow, year level targeting, and category filters for the digital signage display.
          </p>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px] text-[#8f8f8f]">
          <span>{sorted.length} ACTIVE NOTICES</span>
          {fetchedAtLabel && <span className="text-[#4fc3ff]">· UPDATED {fetchedAtLabel.toUpperCase()}</span>}
        </div>
      </div>

      {/* Main 2-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 min-h-0">
        {/* Left Column: Controls & Filters (7 cols) */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          {/* Motion & Sequencing Section */}
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-none p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2">
              <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase">
                MOTION &amp; SEQUENCING
              </span>
              <span className="text-[11px] font-mono font-bold text-[#4fc3ff] uppercase">
                SPEED: {scrollSpeed <= 0.3 ? 'SLOW' : scrollSpeed <= 0.7 ? 'NORMAL' : 'FAST'} ({scrollSpeed.toFixed(2)}x)
              </span>
            </div>

            {/* Slider */}
            <div className="py-2 flex items-center">
              <input
                type="range"
                min="0.1"
                max="2.5"
                step="0.05"
                value={scrollSpeed}
                onChange={e => {
                  const v = parseFloat(e.target.value);
                  setScrollSpeed(v);
                  saveSettings({ scrollSpeed: v });
                }}
                className="w-full h-1 bg-[#1c1c1c] appearance-none cursor-pointer accent-[#4fc3ff]"
              />
            </div>

            {/* Presets */}
            <div className="grid grid-cols-3 gap-2">
              {SPEED_PRESETS.map((p) => (
                <button
                  key={p.label}
                  onClick={() => { setScrollSpeed(p.value); saveSettings({ scrollSpeed: p.value }); }}
                  className={`py-2 px-3 border font-mono text-xs font-bold rounded-none uppercase transition-colors ${
                    scrollSpeed === p.value
                      ? 'bg-[#4fc3ff] text-black border-[#4fc3ff]'
                      : 'bg-[#000000] text-[#8f8f8f] border-[#1c1c1c] hover:text-white hover:border-[#333333]'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Audience & Content Section */}
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-none p-4 flex flex-col gap-4">
            <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase border-b border-[#1c1c1c] pb-2">
              AUDIENCE &amp; CONTENT
            </span>

            {/* Year Level Buttons */}
            <div className="flex flex-col gap-2">
              <label className="text-[10px] font-mono text-[#8f8f8f] uppercase tracking-wider">
                YEAR LEVEL TARGETING
              </label>
              <div className="grid grid-cols-6 gap-2">
                {YEAR_TABS.map(yr => {
                  const active = yearFilter === yr;
                  return (
                    <button
                      key={yr}
                      onClick={() => {
                        setYearFilter(yr);
                        saveSettings({ yearFilter: yr });
                      }}
                      className={`py-2 px-1 border font-mono text-xs font-bold rounded-none uppercase transition-colors text-center ${
                        active
                          ? 'bg-[#4fc3ff] text-black border-[#4fc3ff]'
                          : 'bg-[#000000] text-[#8f8f8f] border-[#1c1c1c] hover:text-white hover:border-[#333333]'
                      }`}
                    >
                      {yr === 'All' ? 'ALL' : `Y${yr}`}
                    </button>
                  );
                })}
              </div>

              {/* Class Name Input for Year 9 or Year 10 */}
              {(yearFilter === '9' || yearFilter === '10') && (
                <motion.div 
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex flex-col gap-1.5 pt-2 border-t border-[#1c1c1c] mt-1"
                >
                  <label className="text-[10px] font-mono text-[#4fc3ff] uppercase tracking-wider flex items-center justify-between">
                    <span>CLASS NAME / FORM CLASS</span>
                    <span className="text-[9px] text-[#8f8f8f]">e.g. {yearFilter === '9' ? '9SR, 9ST, 9CR, 9EA' : '10TE, 10ST, 10FE'}</span>
                  </label>
                  <input
                    type="text"
                    placeholder={`e.g. ${yearFilter === '9' ? '9SR' : '10TE'}`}
                    value={className}
                    onChange={e => {
                      const val = e.target.value.toUpperCase().trim();
                      setClassName(val);
                      
                      // Auto-add class code to keyword boost tags if provided
                      let nextKeywords = keywords;
                      if (val && !keywords.includes(val.toLowerCase())) {
                        nextKeywords = [...keywords, val.toLowerCase()];
                        setKeywords(nextKeywords);
                      }
                      
                      saveSettings({ className: val, keywordFilter: nextKeywords });
                    }}
                    className="w-full bg-[#000000] border border-[#4fc3ff]/50 rounded-none px-3 py-2 text-xs text-white uppercase placeholder-[#555] font-mono focus:outline-none focus:border-[#4fc3ff]"
                  />
                  <p className="text-[10px] text-[#8f8f8f] font-mono italic">
                    Entering your class code enables automatic room change alerts and keyword matching for Year {yearFilter} notices.
                  </p>
                </motion.div>
              )}
            </div>

            {/* Keyword Boost Tag Input */}
            <div className="flex flex-col gap-2 pt-2 border-t border-[#1c1c1c]">
              <label className="text-[10px] font-mono text-[#8f8f8f] uppercase tracking-wider">
                KEYWORD BOOST
              </label>

              {/* Tag pills */}
              {keywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {keywords.map((kw) => (
                    <motion.span
                      key={kw}
                      layout
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      className="group relative inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#0d1a26] border border-[#4fc3ff]/30 text-[#4fc3ff] font-mono text-[10px] uppercase font-bold select-none"
                    >
                      {kw}
                      <button
                        onClick={() => {
                          const next = keywords.filter(k => k !== kw);
                          setKeywords(next);
                          saveSettings({ keywordFilter: next });
                        }}
                        className="opacity-0 group-hover:opacity-100 transition-opacity ml-0.5 text-[#4fc3ff] hover:text-white leading-none"
                        aria-label={`Remove ${kw}`}
                      >
                        ✕
                      </button>
                    </motion.span>
                  ))}
                </div>
              )}

              {/* Input */}
              <input
                type="text"
                placeholder="Type a keyword and press Enter"
                value={keywordInput}
                onChange={e => setKeywordInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    const tag = keywordInput.trim().toLowerCase();
                    if (tag && !keywords.includes(tag)) {
                      const next = [...keywords, tag];
                      setKeywords(next);
                      saveSettings({ keywordFilter: next });
                    }
                    setKeywordInput('');
                  } else if (e.key === 'Backspace' && keywordInput === '' && keywords.length > 0) {
                    const next = keywords.slice(0, -1);
                    setKeywords(next);
                    saveSettings({ keywordFilter: next });
                  }
                }}
                className="w-full bg-[#000000] border border-[#1c1c1c] rounded-none px-3 py-2.5 text-xs text-white placeholder-[#555] font-mono focus:outline-none focus:border-[#4fc3ff]"
              />
              <p className="text-[11px] text-[#666] font-mono italic">
                Notices matching these keywords float to the top of the list.
              </p>
            </div>
          </div>
        </div>

        {/* Right Column: Category Order (5 cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Drag-to-reorder Category List */}
          <div className="bg-[#0a0a0a] border border-[#1c1c1c] rounded-none p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2">
              <span className="text-[11px] font-mono font-bold tracking-widest text-[#8f8f8f] uppercase">
                CATEGORY ORDER
              </span>
              <span className="text-[10px] font-mono text-[#555] uppercase">DRAG TO REORDER</span>
            </div>

            <Reorder.Group
              axis="y"
              values={catOrder}
              onReorder={(newOrder) => {
                setCatOrder(newOrder);
                saveSettings({ catOrder: newOrder });
              }}
              className="flex flex-col gap-1.5"
            >
              {catOrder.map((cat) => {
                const colors = CATEGORY_COLORS[cat] || CATEGORY_COLORS['General'];
                return (
                  <Reorder.Item
                    key={cat}
                    value={cat}
                    className="flex items-center justify-between px-3 py-2.5 border bg-[#000000] border-[#1c1c1c] cursor-grab active:cursor-grabbing border-l-4 group"
                    style={{ borderLeftColor: colors.accent }}
                    whileDrag={{
                      scale: 1.02,
                      backgroundColor: '#141414',
                      boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                      zIndex: 50,
                    }}
                  >
                    <div className="flex items-center gap-2.5">
                      <svg width="10" height="14" viewBox="0 0 10 14" fill="none" className="text-[#555] group-hover:text-[#8f8f8f] transition-colors shrink-0">
                        <circle cx="2" cy="2" r="1.5" fill="currentColor"/>
                        <circle cx="8" cy="2" r="1.5" fill="currentColor"/>
                        <circle cx="2" cy="7" r="1.5" fill="currentColor"/>
                        <circle cx="8" cy="7" r="1.5" fill="currentColor"/>
                        <circle cx="2" cy="12" r="1.5" fill="currentColor"/>
                        <circle cx="8" cy="12" r="1.5" fill="currentColor"/>
                      </svg>
                      <span className="text-xs font-mono font-bold uppercase text-white">{cat}</span>
                    </div>
                    <span
                      className="text-[10px] font-mono uppercase"
                      style={{ color: colors.accent, opacity: 0.7 }}
                    >
                      {catOrder.indexOf(cat) + 1}
                    </span>
                  </Reorder.Item>
                );
              })}
            </Reorder.Group>

            <p className="text-[11px] font-mono text-[#555] italic border-t border-[#1c1c1c] pt-2">
              Order determines priority on the mirror display. Drag rows to reorder.
            </p>
          </div>
        </div>
      </div>

      {/* Bottom Actions Bar */}
      <div className="flex items-center justify-between pt-4 border-t border-[#1c1c1c] mt-6 shrink-0">
        <span className="text-xs font-mono text-[#666]">
          CHANGES AUTO-SAVED TO LOCAL CONFIG
        </span>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setCatFilters(ALL_CATEGORIES);
              setCatOrder(ALL_CATEGORIES);
              setYearFilter('All');
              setClassName('');
              setKeywords([]);
              setKeywordInput('');
              setScrollSpeed(0.5);
              saveSettings({ catFilters: ALL_CATEGORIES, catOrder: ALL_CATEGORIES, yearFilter: 'All', className: '', keywordFilter: [], scrollSpeed: 0.5 });
            }}
            className="px-4 py-2 border border-[#1c1c1c] hover:border-[#333] text-[#8f8f8f] hover:text-white font-mono text-xs font-bold rounded-none uppercase transition-colors"
          >
            RESET
          </button>
          <button
            onClick={() => saveSettings({ catFilters, catOrder, yearFilter, className, keywordFilter: keywords, scrollSpeed })}
            className="px-5 py-2 bg-[#4fc3ff] text-black hover:bg-[#7dd3fc] font-mono text-xs font-bold rounded-none uppercase transition-colors"
          >
            APPLY
          </button>
        </div>
      </div>
    </div>
  );
}