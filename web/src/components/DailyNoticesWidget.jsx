import { useEffect, useRef, useState, useCallback } from 'react';
import { motion, Reorder, AnimatePresence } from 'framer-motion';
import { useLanguage } from '../contexts/LanguageContext';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

// Category colour palette (exact match for both badges, left borders, and filter settings)
export const CATEGORY_COLORS = {
  'General':        { bg: 'rgba(148,163,184,0.15)', accent: '#94a3b8', text: '#cbd5e1' },
  'Sports':         { bg: 'rgba(34,197,94,0.15)',   accent: '#22c55e', text: '#86efac' },
  'Meetings':       { bg: 'rgba(139,92,246,0.15)',  accent: '#8b5cf6', text: '#c4b5fd' },
  'Academic':       { bg: 'rgba(59,130,246,0.15)',  accent: '#3b82f6', text: '#93c5fd' },
  'Careers':        { bg: 'rgba(251,191,36,0.15)',  accent: '#fbbf24', text: '#fde68a' },
  'Arts & Culture': { bg: 'rgba(244,63,94,0.15)',   accent: '#f43f5e', text: '#fda4af' },
  'Service':        { bg: 'rgba(20,184,166,0.15)',  accent: '#14b8a6', text: '#5eead4' },
};

const ALL_CATEGORIES = ['General', 'Sports', 'Meetings', 'Academic', 'Careers', 'Arts & Culture', 'Service'];
const YEAR_TABS = ['All', '9', '10', '11', '12', '13'];

const SPEED_PRESETS = [
  { labelKey: 'slow',   value: 0.25 },
  { labelKey: 'normal', value: 0.5  },
  { labelKey: 'fast',   value: 1.0  },
];

/** Extract key details from HTML */
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

  if (dateMatch) details.date = dateMatch[0].trim();
  if (timeMatch) details.time = timeMatch[0].trim();
  if (roomMatch) details.location = roomMatch[0].trim();
  return details;
}

/** Build a preview snippet */
function buildPreview(html, maxLen = 130) {
  if (!html) return '';
  const text = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  return text.length > maxLen ? text.slice(0, maxLen).trimEnd() + '…' : text;
}

/** Notice Card with Left Color Outline Accent */
function NoticeCard({ n, onClick }) {
  const { t, translateNoticeText } = useLanguage();
  const isUrgent = n.importance === 'high';
  const cat = n.category || 'General';
  const catColors = CATEGORY_COLORS[cat] || CATEGORY_COLORS['General'];

  const previewText = translateNoticeText(buildPreview(n.notice, 130));
  const translatedTitle = translateNoticeText(n.title);
  const dateStr = n.details?.date ? ` · ${n.details.date}` : ` · ${t('today')}`;

  return (
    <article
      onClick={onClick}
      style={{ borderLeft: `4px solid ${isUrgent ? '#ef4444' : catColors.accent}` }}
      className="bg-[#0e0e0e] hover:bg-[#161616] p-4 flex flex-col gap-2 transition-all cursor-pointer group rounded-none select-none relative"
    >
      <div className="text-[11px] font-bold tracking-wider uppercase font-mono flex items-center justify-between">
        <span
          className="px-2 py-0.5 rounded-none text-[10px] font-mono font-bold"
          style={{
            backgroundColor: isUrgent ? 'rgba(239,68,68,0.2)' : catColors.bg,
            color: isUrgent ? '#ef4444' : catColors.accent,
          }}
        >
          {isUrgent ? t('urgent') : cat.toUpperCase()}{dateStr}
        </span>
        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] font-mono text-[#888888] group-hover:text-white uppercase font-bold">
          {t('read')}
        </span>
      </div>

      <h4 className="text-[18px] font-bold text-white leading-snug group-hover:text-[#ffffff] transition-colors">
        {translatedTitle}
      </h4>

      <p className="text-[14px] text-[#b0b0b0] leading-relaxed line-clamp-3 font-sans">
        {previewText}
      </p>

      {n.contact && (
        <div className="text-[10px] text-[#777777] font-mono mt-0.5 uppercase">
          {t('see')} {n.contact}
        </div>
      )}
    </article>
  );
}

/** In-Place Expanded Notice View (Fills notices panel, clicking closes it) */
function ExpandedNoticeView({ notice, onClose }) {
  const { t, translateNoticeText } = useLanguage();
  const isUrgent = notice.importance === 'high';
  const cat = notice.category || 'General';
  const catColors = CATEGORY_COLORS[cat] || CATEGORY_COLORS['General'];

  const rawBody = (notice.notice || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  const translatedBody = translateNoticeText(rawBody);
  const translatedTitle = translateNoticeText(notice.title);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.2 }}
      onClick={onClose}
      style={{ borderLeft: `5px solid ${isUrgent ? '#ef4444' : catColors.accent}` }}
      className="flex-1 flex flex-col p-6 bg-[#0c0c0c] overflow-y-auto custom-scrollbar cursor-pointer select-none rounded-none"
    >
      {/* Top Bar */}
      <div className="flex items-center justify-between pb-4 border-b border-[#222222] shrink-0">
        <div className="flex items-center gap-3">
          <span
            className="px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider rounded-none font-mono"
            style={{
              backgroundColor: isUrgent ? 'rgba(239,68,68,0.2)' : catColors.bg,
              color: isUrgent ? '#ef4444' : catColors.accent,
            }}
          >
            {isUrgent ? t('urgent') : cat.toUpperCase()}
          </span>
          <span className="text-xs text-[#888888] font-mono">
            {notice.details?.date || t('today')}
          </span>
        </div>
      </div>

      {/* Big Clear Title */}
      <div className="py-5">
        <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight leading-snug">
          {translatedTitle}
        </h2>
      </div>

      {/* Key Details Strip (If present) */}
      {(notice.details?.time || notice.details?.location || notice.contact) && (
        <div className="flex flex-wrap gap-4 py-3 border-y border-[#1c1c1c] text-xs font-mono text-[#888888] shrink-0">
          {notice.details?.time && (
            <span>TIME: <strong className="text-white">{notice.details.time}</strong></span>
          )}
          {notice.details?.location && (
            <span>LOCATION: <strong className="text-white">{translateNoticeText(notice.details.location)}</strong></span>
          )}
          {notice.contact && (
            <span>CONTACT: <strong className="text-white">{notice.contact}</strong></span>
          )}
        </div>
      )}

      {/* Clear Big Full Notice Text (No quick brief box) */}
      <div className="py-6 flex-1">
        <div className="text-base sm:text-lg text-[#e0e0e0] leading-relaxed whitespace-pre-line font-sans">
          {translatedBody}
        </div>
      </div>

      {/* Bottom Close Cue */}
      <div className="pt-4 border-t border-[#1c1c1c] text-center text-xs font-mono text-[#777777] uppercase tracking-wider shrink-0">
        [ {t('click_anywhere_close')} ]
      </div>
    </motion.div>
  );
}

export default function DailyNoticesWidget({ widget = {}, onUpdateData }) {
  const { t } = useLanguage();
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fetchedAt, setFetchedAt] = useState(null);
  const [selectedNotice, setSelectedNotice] = useState(null);
  const [showFilters, setShowFilters] = useState(false);

  const getCachedConfig = () => {
    try {
      const saved = localStorage.getItem('notices_widget_config');
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  };
  const cachedConfig = getCachedConfig();

  // Search query & filter controls state
  const [searchQuery, setSearchQuery] = useState('');

  // Applied filter & display settings (governs notices list, active filtering, and auto-scroll)
  const [appliedYearFilter, setAppliedYearFilter] = useState(() => widget.data?.yearFilter || cachedConfig.yearFilter || 'All');
  const [appliedCatFilters, setAppliedCatFilters] = useState(() => widget.data?.catFilters ?? cachedConfig.catFilters ?? ALL_CATEGORIES);
  const [appliedCatOrder, setAppliedCatOrder] = useState(() => widget.data?.catOrder ?? cachedConfig.catOrder ?? ALL_CATEGORIES);
  const [appliedKeywords, setAppliedKeywords] = useState(() => {
    const kf = widget.data?.keywordFilter ?? cachedConfig.keywordFilter;
    if (Array.isArray(kf)) return kf;
    if (typeof kf === 'string' && kf.trim()) return kf.split(',').map(k => k.trim()).filter(Boolean);
    return [];
  });
  const [appliedClassName, setAppliedClassName] = useState(() => widget.data?.className || cachedConfig.className || '');
  const [appliedScrollSpeed, setAppliedScrollSpeed] = useState(() => widget.data?.scrollSpeed ?? cachedConfig.scrollSpeed ?? 0.5);

  // Draft filter & display settings (isolated to the settings panel; only committed when user clicks "APPLY CHANGES")
  const [draftYearFilter, setDraftYearFilter] = useState(appliedYearFilter);
  const [draftCatFilters, setDraftCatFilters] = useState(appliedCatFilters);
  const [draftCatOrder, setDraftCatOrder] = useState(appliedCatOrder);
  const [draftKeywords, setDraftKeywords] = useState(appliedKeywords);
  const [draftKeywordInput, setDraftKeywordInput] = useState('');
  const [draftClassName, setDraftClassName] = useState(appliedClassName);
  const [draftScrollSpeed, setDraftScrollSpeed] = useState(appliedScrollSpeed);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Auto-scroll ref and timer management
  const scrollRef = useRef(null);
  const isProgrammaticScroll = useRef(false);
  const scrollState = useRef({
    scrollInterval: null,
    holdTimer: null,
    resumeTimer: null,
  });

  // ── Load notices ───────────────────────────────────────────────────────────
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
          const noticeList = Array.isArray(data) ? data : (data.notices || []);
          const fetchedAtVal = data.fetchedAtHuman || data.fetchedAt || null;
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

  // ── Load config from server ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const fetchConfig = async () => {
      try {
        const res = await fetch(`${API_URL}/api/notices/config`);
        if (res.ok) {
          const cfg = await res.json();
          if (!cancelled && cfg) {
            if (cfg.yearFilter) {
              setAppliedYearFilter(cfg.yearFilter);
              setDraftYearFilter(cfg.yearFilter);
            }
            if (cfg.catFilters) {
              setAppliedCatFilters(cfg.catFilters);
              setDraftCatFilters(cfg.catFilters);
            }
            if (cfg.catOrder) {
              setAppliedCatOrder(cfg.catOrder);
              setDraftCatOrder(cfg.catOrder);
            }
            if (cfg.keywordFilter) {
              const kf = cfg.keywordFilter;
              const parsed = Array.isArray(kf) ? kf : (typeof kf === 'string' && kf.trim() ? kf.split(',').map(k => k.trim()).filter(Boolean) : []);
              setAppliedKeywords(parsed);
              setDraftKeywords(parsed);
            }
            if (cfg.className !== undefined) {
              setAppliedClassName(cfg.className);
              setDraftClassName(cfg.className);
            }
            if (cfg.scrollSpeed !== undefined) {
              setAppliedScrollSpeed(cfg.scrollSpeed);
              setDraftScrollSpeed(cfg.scrollSpeed);
            }
            try { localStorage.setItem('notices_widget_config', JSON.stringify(cfg)); } catch {}
          }
        }
      } catch { /* fallback to local storage */ }
    };
    fetchConfig();
    return () => { cancelled = true; };
  }, []);

  // ── Persist settings ───────────────────────────────────────────────────────
  const saveSettings = async (updates) => {
    try {
      const current = getCachedConfig();
      const next = { ...current, ...updates };
      localStorage.setItem('notices_widget_config', JSON.stringify(next));

      const payload = {
        yearFilter: next.yearFilter ?? appliedYearFilter,
        className: next.className ?? appliedClassName,
        catFilters: next.catFilters ?? appliedCatFilters,
        catOrder: next.catOrder ?? appliedCatOrder,
        keywordFilter: next.keywordFilter ?? next.keywords ?? appliedKeywords,
        scrollSpeed: next.scrollSpeed ?? appliedScrollSpeed,
      };
      await fetch(`${API_URL}/api/notices/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch(() => {});

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch { /* silent */ }
    if (onUpdateData) onUpdateData({ ...widget.data, ...updates });
  };

  // ── Compare arrays for equality ────────────────────────────────────────────
  const areArraysEqual = (a, b) => {
    if (a === b) return true;
    if (!a || !b) return false;
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  };

  // ── Check if draft settings differ from applied configuration ─────────────
  const hasChanges = (
    draftYearFilter !== appliedYearFilter ||
    draftClassName !== appliedClassName ||
    Math.abs(draftScrollSpeed - appliedScrollSpeed) > 0.001 ||
    !areArraysEqual(draftKeywords, appliedKeywords) ||
    !areArraysEqual(draftCatFilters, appliedCatFilters) ||
    !areArraysEqual(draftCatOrder, appliedCatOrder)
  );

  // ── Apply changes explicitly ──────────────────────────────────────────────
  const handleApplyChanges = async () => {
    if (!hasChanges) return;

    const updates = {
      yearFilter: draftYearFilter,
      className: draftClassName,
      catFilters: draftCatFilters,
      catOrder: draftCatOrder,
      keywordFilter: draftKeywords,
      scrollSpeed: draftScrollSpeed,
    };

    // Commit to applied state so notices view updates
    setAppliedYearFilter(draftYearFilter);
    setAppliedClassName(draftClassName);
    setAppliedCatFilters(draftCatFilters);
    setAppliedCatOrder(draftCatOrder);
    setAppliedKeywords(draftKeywords);
    setAppliedScrollSpeed(draftScrollSpeed);

    await saveSettings(updates);
  };

  // ── Settings navigation handlers ──────────────────────────────────────────
  const handleOpenSettings = () => {
    setSelectedNotice(null);
    // Reset draft buffer to match current applied values
    setDraftYearFilter(appliedYearFilter);
    setDraftClassName(appliedClassName);
    setDraftCatFilters(appliedCatFilters);
    setDraftCatOrder(appliedCatOrder);
    setDraftKeywords(appliedKeywords);
    setDraftKeywordInput('');
    setDraftScrollSpeed(appliedScrollSpeed);
    setShowFilters(true);
  };

  const handleCloseSettings = () => {
    // Discard any unapplied draft changes
    setDraftYearFilter(appliedYearFilter);
    setDraftClassName(appliedClassName);
    setDraftCatFilters(appliedCatFilters);
    setDraftCatOrder(appliedCatOrder);
    setDraftKeywords(appliedKeywords);
    setDraftKeywordInput('');
    setDraftScrollSpeed(appliedScrollSpeed);
    setShowFilters(false);
  };

  const handleToggleSettings = () => {
    if (showFilters) {
      handleCloseSettings();
    } else {
      handleOpenSettings();
    }
  };

  // ── Enrich notices ─────────────────────────────────────────────────────────
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

  // ── Filter notices (uses APPLIED settings only) ───────────────────────────
  const filtered = enriched.filter(n => {
    if (appliedYearFilter !== 'All') {
      const matchesYear = n.targetYears.includes('All') || n.targetYears.includes(appliedYearFilter);
      if (!matchesYear) return false;
    }
    if (!appliedCatFilters.includes(n.category)) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const haystack = `${n.title} ${n.category} ${n.contact} ${(n.notice || '').replace(/<[^>]*>/g, ' ')}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  // ── Sort: Urgent first, then Keyword match score, then Category priority ──
  const keywordTerms = appliedKeywords.map(k => k.toLowerCase());
  const getKeywordScore = (n) => {
    if (keywordTerms.length === 0) return 0;
    const haystack = `${n.title} ${n.category} ${n.contact} ${(n.notice || '').replace(/<[^>]*>/g, ' ')}`.toLowerCase();
    return keywordTerms.filter(kw => haystack.includes(kw)).length;
  };
  const getCatOrderScore = (n) => {
    const idx = appliedCatOrder.indexOf(n.category);
    return idx === -1 ? appliedCatOrder.length : idx;
  };

  const sorted = [...filtered].sort((a, b) => {
    if (a.importance === 'high' && b.importance !== 'high') return -1;
    if (b.importance === 'high' && a.importance !== 'high') return 1;
    const scoreA = getKeywordScore(a);
    const scoreB = getKeywordScore(b);
    if (scoreB !== scoreA) return scoreB - scoreA;
    return getCatOrderScore(a) - getCatOrderScore(b);
  });

  // ── Auto-scroll with 3-second pause on user interaction ────────────────────
  const startScroll = useCallback(() => {
    const state = scrollState.current;
    if (state.scrollInterval) {
      clearInterval(state.scrollInterval);
      state.scrollInterval = null;
    }
    if (state.holdTimer) {
      clearTimeout(state.holdTimer);
      state.holdTimer = null;
    }

    if (showFilters || selectedNotice || loading || error || sorted.length === 0) return;

    const SPEED = appliedScrollSpeed;
    const INTERVAL = 25;
    const HOLD_TOP = 4000;
    const HOLD_BTM = 2000;

    state.holdTimer = setTimeout(() => {
      state.scrollInterval = setInterval(() => {
        const el = scrollRef.current;
        if (!el) return;
        const max = el.scrollHeight - el.clientHeight;
        if (max <= 0) {
          if (state.scrollInterval) clearInterval(state.scrollInterval);
          return;
        }
        if (el.scrollTop >= max - 1) {
          if (state.scrollInterval) {
            clearInterval(state.scrollInterval);
            state.scrollInterval = null;
          }
          state.holdTimer = setTimeout(() => {
            if (scrollRef.current) {
              isProgrammaticScroll.current = true;
              scrollRef.current.scrollTop = 0;
              setTimeout(() => { isProgrammaticScroll.current = false; }, 50);
            }
            startScroll();
          }, HOLD_BTM);
        } else {
          isProgrammaticScroll.current = true;
          el.scrollTop += SPEED;
          setTimeout(() => { isProgrammaticScroll.current = false; }, 10);
        }
      }, INTERVAL);
    }, HOLD_TOP);
  }, [showFilters, selectedNotice, loading, error, sorted.length, appliedScrollSpeed]);

  useEffect(() => {
    startScroll();
    return () => {
      const state = scrollState.current;
      if (state.scrollInterval) clearInterval(state.scrollInterval);
      if (state.holdTimer) clearTimeout(state.holdTimer);
      if (state.resumeTimer) clearTimeout(state.resumeTimer);
    };
  }, [startScroll]);

  // Handle user scroll interaction: pause immediately, wait 3 seconds after scrolling stops
  const handleUserInteraction = () => {
    if (isProgrammaticScroll.current) return;
    const state = scrollState.current;
    if (state.scrollInterval) {
      clearInterval(state.scrollInterval);
      state.scrollInterval = null;
    }
    if (state.holdTimer) {
      clearTimeout(state.holdTimer);
      state.holdTimer = null;
    }
    if (state.resumeTimer) {
      clearTimeout(state.resumeTimer);
    }

    // Set 3 seconds (3000ms) timer before resuming auto-scroll
    state.resumeTimer = setTimeout(() => {
      startScroll();
    }, 3000);
  };

  // Format fetched timestamp
  const formatFetchedAt = (val) => {
    if (!val) return null;
    if (typeof val === 'string' && (val.includes(',') || val.includes('AM') || val.includes('PM'))) {
      return val;
    }
    try {
      return new Date(val).toLocaleString('en-NZ', {
        weekday: 'short', day: 'numeric', month: 'short',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return val; }
  };
  const fetchedAtLabel = formatFetchedAt(fetchedAt);

  return (
    <section className="h-full flex flex-col p-5 select-none min-h-0 bg-[#000000] font-mono">
      {/* HEADER: Highly Obvious Button to Toggle Settings */}
      <div className="flex items-center justify-between mb-3 pb-3 border-b border-[#222222] shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-white uppercase tracking-wider">
            {t('notices')}
          </h2>
          <span className="text-xs text-[#888888]">
            ({sorted.length} {t('today')})
          </span>
        </div>

        {/* PROMINENT SETTINGS TOGGLE BUTTON */}
        <button
          type="button"
          onClick={handleToggleSettings}
          className={`px-3.5 py-1.5 border font-mono text-xs font-bold uppercase tracking-wider transition-all cursor-pointer rounded-none flex items-center gap-2 ${
            showFilters
              ? 'bg-white text-black border-white'
              : 'bg-[#141414] text-white border-[#333333] hover:border-white hover:bg-[#202020]'
          }`}
          title="Click to configure display and filters"
        >
          <span className="material-symbols-outlined text-sm">tune</span>
          <span>{showFilters ? t('back_to_notices') : t('filter_settings')}</span>
        </button>
      </div>

      {/* VIEW 1: EXPANDED NOTICE VIEW (In-place expansion, NO modal) */}
      <AnimatePresence mode="wait">
        {selectedNotice ? (
          <ExpandedNoticeView
            key={selectedNotice.id}
            notice={selectedNotice}
            onClose={() => setSelectedNotice(null)}
          />
        ) : showFilters ? (
          /* VIEW 2: FILTER & DISPLAY SETTINGS (Edits draft values only) */
          <div key="filters-panel" className="flex-1 flex flex-col gap-5 overflow-y-auto custom-scrollbar pr-1">
            <div className="flex items-center justify-between pb-2 border-b border-[#1c1c1c]">
              <span className="text-xs font-bold uppercase tracking-wider text-white">
                {t('filter_settings')}
              </span>
            </div>

            {/* Motion & Speed */}
            <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2">
                <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase">
                  {t('motion_speed')}
                </span>
                <span className="text-[11px] font-bold text-white uppercase">
                  {t('speed')}: {draftScrollSpeed <= 0.3 ? t('slow') : draftScrollSpeed <= 0.7 ? t('normal') : t('fast')} ({draftScrollSpeed.toFixed(2)}x)
                </span>
              </div>

              <div className="py-2 flex items-center">
                <input
                  type="range"
                  min="0.1"
                  max="2.5"
                  step="0.05"
                  value={draftScrollSpeed}
                  onChange={e => {
                    const v = parseFloat(e.target.value);
                    setDraftScrollSpeed(v);
                  }}
                  className="w-full h-1 bg-[#222222] appearance-none cursor-pointer accent-white"
                />
              </div>

              <div className="grid grid-cols-3 gap-2">
                {SPEED_PRESETS.map((p) => (
                  <button
                    key={p.labelKey}
                    type="button"
                    onClick={() => setDraftScrollSpeed(p.value)}
                    className={`py-2 px-3 font-mono text-xs font-bold uppercase transition-colors cursor-pointer rounded-none border ${
                      draftScrollSpeed === p.value
                        ? 'bg-white text-black border-white'
                        : 'bg-[#000000] text-[#888888] border-[#222222] hover:text-white hover:border-[#444444]'
                    }`}
                  >
                    {t(p.labelKey)}
                  </button>
                ))}
              </div>
            </div>

            {/* Year Level Targeting */}
            <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
              <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase border-b border-[#1c1c1c] pb-2">
                {t('year')}
              </span>
              <div className="grid grid-cols-6 gap-2">
                {YEAR_TABS.map(yr => (
                  <button
                    key={yr}
                    type="button"
                    onClick={() => setDraftYearFilter(yr)}
                    className={`py-2 px-1 font-mono text-xs font-bold uppercase transition-colors text-center cursor-pointer rounded-none border ${
                      draftYearFilter === yr
                        ? 'bg-white text-black border-white'
                        : 'bg-[#000000] text-[#888888] border-[#222222] hover:text-white hover:border-[#444444]'
                    }`}
                  >
                    {yr === 'All' ? t('all') : `Y${yr}`}
                  </button>
                ))}
              </div>

              {/* Form Class / Class Name */}
              {(draftYearFilter === '9' || draftYearFilter === '10') && (
                <div className="flex flex-col gap-1.5 pt-2 border-t border-[#1c1c1c] mt-1">
                  <label className="text-[10px] text-white uppercase tracking-wider flex items-center justify-between">
                    <span>{t('form_class')}</span>
                    <span className="text-[9px] text-[#777777]">e.g. {draftYearFilter === '9' ? '9SR, 9ST, 9CR' : '10TE, 10ST'}</span>
                  </label>
                  <input
                    type="text"
                    placeholder={`e.g. ${draftYearFilter === '9' ? '9SR' : '10TE'}`}
                    value={draftClassName}
                    onChange={e => {
                      const val = e.target.value.toUpperCase().trim();
                      setDraftClassName(val);
                      if (val && !draftKeywords.includes(val.toLowerCase())) {
                        setDraftKeywords([...draftKeywords, val.toLowerCase()]);
                      }
                    }}
                    className="w-full bg-[#000000] border border-[#333333] px-3 py-2 text-xs text-white uppercase font-mono focus:outline-none focus:border-white rounded-none"
                  />
                </div>
              )}
            </div>

            {/* Keyword Boost (DRAGGABLE REORDERING) */}
            <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2">
                <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase">
                  {t('keyword_boost')}
                </span>
                <span className="text-[10px] text-[#666666] uppercase">{t('drag_to_reorder')}</span>
              </div>

              {draftKeywords.length > 0 && (
                <Reorder.Group
                  axis="x"
                  values={draftKeywords}
                  onReorder={setDraftKeywords}
                  className="flex flex-wrap gap-2"
                >
                  {draftKeywords.map((kw) => (
                    <Reorder.Item
                      key={kw}
                      value={kw}
                      className="cursor-grab active:cursor-grabbing inline-flex items-center gap-1.5 px-3 py-1 bg-[#141414] text-white font-mono text-[11px] uppercase font-bold border border-[#333333] rounded-none hover:border-white"
                      whileDrag={{ scale: 1.05, backgroundColor: '#222222' }}
                    >
                      <span className="text-[#666666] text-xs">⋮⋮</span>
                      <span>{kw}</span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDraftKeywords(draftKeywords.filter(k => k !== kw));
                        }}
                        className="text-[#888888] hover:text-white cursor-pointer ml-1"
                      >
                        ✕
                      </button>
                    </Reorder.Item>
                  ))}
                </Reorder.Group>
              )}

              <input
                type="text"
                placeholder={t('keyword_placeholder')}
                value={draftKeywordInput}
                onChange={e => setDraftKeywordInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    const tag = draftKeywordInput.trim().toLowerCase();
                    if (tag && !draftKeywords.includes(tag)) {
                      setDraftKeywords([...draftKeywords, tag]);
                    }
                    setDraftKeywordInput('');
                  }
                }}
                className="w-full bg-[#000000] border border-[#333333] px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-white rounded-none"
              />
            </div>

            {/* Category Priority Order */}
            <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2">
                <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase">
                  {t('category_order')}
                </span>
                <span className="text-[10px] text-[#666666] uppercase">{t('drag_to_reorder')}</span>
              </div>

              <Reorder.Group
                axis="y"
                values={draftCatOrder}
                onReorder={setDraftCatOrder}
                className="flex flex-col gap-1.5"
              >
                {draftCatOrder.map((cat) => {
                  const colors = CATEGORY_COLORS[cat] || CATEGORY_COLORS['General'];
                  return (
                    <Reorder.Item
                      key={cat}
                      value={cat}
                      className="flex items-center justify-between px-3 py-2 bg-[#000000] border border-[#222222] cursor-grab active:cursor-grabbing rounded-none"
                      whileDrag={{ scale: 1.01, backgroundColor: '#141414' }}
                    >
                      <div className="flex items-center gap-2.5">
                        <span
                          className="w-2.5 h-2.5 rounded-none shrink-0"
                          style={{ backgroundColor: colors.accent }}
                        />
                        <span className="text-xs font-mono font-bold uppercase text-white">{cat}</span>
                      </div>
                      <span
                        className="text-[10px] font-mono uppercase"
                        style={{ color: colors.accent }}
                      >
                        {draftCatOrder.indexOf(cat) + 1}
                      </span>
                    </Reorder.Item>
                  );
                })}
              </Reorder.Group>
            </div>

            {/* Actions: Apply changes only when user clicks, disabled if no changes */}
            <div className="flex items-center justify-between pt-3 border-t border-[#1c1c1c] shrink-0">
              <button
                type="button"
                onClick={() => {
                  setDraftCatFilters(ALL_CATEGORIES);
                  setDraftCatOrder(ALL_CATEGORIES);
                  setDraftYearFilter('All');
                  setDraftClassName('');
                  setDraftKeywords([]);
                  setDraftKeywordInput('');
                  setDraftScrollSpeed(0.5);
                }}
                className="px-4 py-2 border border-[#222222] hover:border-[#444444] text-[#888888] hover:text-white font-mono text-xs font-bold uppercase transition-colors cursor-pointer rounded-none"
              >
                {t('reset')}
              </button>
              <button
                type="button"
                onClick={handleApplyChanges}
                disabled={!hasChanges}
                className={`px-6 py-2.5 font-mono text-xs font-bold uppercase transition-all rounded-none border ${
                  hasChanges
                    ? 'bg-white text-black border-white hover:bg-[#e0e0e0] cursor-pointer'
                    : 'bg-[#141414] text-[#555555] border-[#222222] cursor-not-allowed opacity-40 select-none'
                }`}
                title={hasChanges ? 'Apply changes to notices' : 'No changes to apply'}
              >
                {saveSuccess ? (t('changes_applied') || 'CHANGES APPLIED') : (t('apply_changes') || 'APPLY CHANGES')}
              </button>
            </div>
          </div>
        ) : (
          /* VIEW 3: ACTIVE NOTICES LIST (Default view with reliable auto-scroll) */
          <div
            key="notices-list"
            ref={scrollRef}
            onWheel={handleUserInteraction}
            onTouchMove={handleUserInteraction}
            onPointerDown={handleUserInteraction}
            className="flex-1 flex flex-col gap-2.5 overflow-y-auto custom-scrollbar min-h-0 pr-1"
          >
            {loading ? (
              <div className="flex flex-col gap-2.5 overflow-hidden">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-[#0e0e0e] p-4 flex flex-col gap-2 animate-pulse rounded-none">
                    <div className="h-3 w-20 bg-[#1c1c1c]"></div>
                    <div className="h-5 w-3/4 bg-[#262626]"></div>
                    <div className="h-3.5 w-full bg-[#161616]"></div>
                  </div>
                ))}
              </div>
            ) : sorted.length === 0 ? (
              <div className="py-12 text-center text-[#777777] text-xs uppercase font-mono">
                {t('no_notices')}
              </div>
            ) : (
              sorted.map((n, idx) => (
                <NoticeCard
                  key={n.id || idx}
                  n={n}
                  onClick={() => setSelectedNotice(n)}
                />
              ))
            )}
          </div>
        )}
      </AnimatePresence>
    </section>
  );
}