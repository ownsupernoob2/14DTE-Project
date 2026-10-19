import { useEffect, useState, useCallback } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { motion } from 'framer-motion';
import { useLanguage } from '../contexts/LanguageContext';
import step1Img from '../assets/timetable-instructions/1.png';
import step2Img from '../assets/timetable-instructions/2.png';

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

// ── Slideshow Steps for Setup Modal with Real Screenshots & Redirect Link ───
export function TimetableSetupModal({ isOpen, onClose, onSave, saving, error, currentUrl }) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [urlInput, setUrlInput] = useState(currentUrl || '');
  const [localError, setLocalError] = useState(null);
  const { t } = useLanguage();

  const slides = [
    {
      step: 1,
      title: 'CLICK LINK & SIGN IN TO SCHOOL KAMAR',
      desc: 'Click on the link below and sign in to your school KAMAR portal using your student login:',
      isLink: true,
    },
    {
      step: 2,
      title: 'CLICK ON "TIMETABLE AND ATTENDANCE"',
      desc: 'After signing in, click on the "Timetable and Attendance" tile on your portal dashboard:',
      img: step1Img,
    },
    {
      step: 3,
      title: 'SCROLL DOWN AND COPY THE .ICS URL',
      desc: 'Scroll down to the bottom of the page and copy the URL ending in .ics circled below:',
      img: step2Img,
    },
    {
      step: 4,
      title: 'PASTE URL BELOW AND SUBMIT',
      desc: 'Paste the copied .ics address directly into the field below and click SAVE TIMETABLE:',
      isArrow: true,
    },
  ];

  useEffect(() => {
    if (isOpen) {
      setUrlInput(currentUrl || '');
      setLocalError(null);
      setCurrentSlide(0);
    }
  }, [isOpen, currentUrl]);

  if (!isOpen) return null;

  const slide = slides[currentSlide];

  const handleNext = () => {
    if (currentSlide < slides.length - 1) {
      setCurrentSlide(s => s + 1);
    }
  };

  const handlePrev = () => {
    if (currentSlide > 0) {
      setCurrentSlide(s => s - 1);
    }
  };

  const handleSubmit = (e) => {
    e?.preventDefault();
    const trimmed = urlInput.trim();
    if (!trimmed) {
      setLocalError('Please enter an .ics link');
      return;
    }
    if (!isValidKingsHighUrl(trimmed)) {
      setLocalError('Link must start with https://kingshigh.school.kiwi/ics/ and end with .ics');
      return;
    }
    setLocalError(null);
    onSave(trimmed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.97 }}
        className="bg-[#0a0a0a] border border-[#222222] rounded-none w-full max-w-xl p-6 flex flex-col gap-5 text-white font-mono shadow-2xl select-none"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-3">
          <span className="text-xs font-bold uppercase tracking-wider text-white">
            {t('set_up_timetable')}
          </span>
          <button
            onClick={onClose}
            className="text-[#888888] hover:text-white text-xs font-mono uppercase cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Slideshow Display Area */}
        <div className="bg-[#0e0e0e] p-5 flex flex-col gap-3 rounded-none border border-[#1a1a1a]">
          {/* Step indicator header */}
          <div className="flex items-center justify-between text-[11px] text-[#888888]">
            <span className="uppercase font-bold tracking-widest text-white">
              {t('slideshow_step')} {slide.step} / {slides.length}
            </span>
            <div className="flex gap-1.5">
              {slides.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => setCurrentSlide(idx)}
                  className={`w-6 h-1 transition-colors cursor-pointer ${
                    idx === currentSlide ? 'bg-white' : 'bg-[#2a2a2a] hover:bg-[#444444]'
                  }`}
                />
              ))}
            </div>
          </div>

          {/* Slide Title and Description */}
          <div className="flex flex-col gap-1">
            <h3 className="text-xs font-bold text-white uppercase tracking-tight">
              {slide.title}
            </h3>
            <p className="text-xs text-[#aaaaaa] leading-relaxed">
              {slide.desc}
            </p>
          </div>

          {/* Slide Visual Content */}
          <div className="py-2 flex flex-col items-center justify-center min-h-[140px] bg-[#000000] border border-[#1c1c1c] p-2">
            {slide.isLink && (
              <div className="flex flex-col items-center gap-3 p-4 text-center">
                <span className="text-xs text-[#888888]">Official School Portal Redirect:</span>
                <a
                  href="https://kingshigh.school.kiwi"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-5 py-2.5 bg-white text-black font-mono text-xs font-bold uppercase tracking-wider hover:bg-[#e0e0e0] flex items-center gap-2 transition-all cursor-pointer rounded-none"
                >
                  <span>OPEN KINGSHIGH.SCHOOL.KIWI</span>
                  <span className="material-symbols-outlined text-sm">open_in_new</span>
                </a>
              </div>
            )}

            {slide.img && (
              <img
                src={slide.img}
                alt={slide.title}
                className="w-full max-h-52 object-contain"
              />
            )}

            {slide.isArrow && (
              <div className="flex flex-col items-center gap-2 py-4">
                <span className="text-xs text-[#aaaaaa]">PASTE URL BELOW:</span>
                <span className="text-3xl text-white animate-bounce">↓</span>
              </div>
            )}
          </div>

          {/* Slideshow Navigation Buttons */}
          <div className="flex items-center justify-between pt-1">
            <button
              type="button"
              onClick={handlePrev}
              disabled={currentSlide === 0}
              className="px-6 py-3 border border-[#333333] disabled:opacity-20 text-xs font-mono font-bold uppercase hover:border-[#666666] text-[#aaaaaa] hover:text-white transition-colors cursor-pointer rounded-none"
            >
              ← {t('prev')}
            </button>
            <button
              type="button"
              onClick={handleNext}
              disabled={currentSlide === slides.length - 1}
              className="px-10 py-3.5 bg-white disabled:opacity-20 text-black hover:bg-[#e0e0e0] text-sm font-mono font-bold uppercase tracking-wider transition-all cursor-pointer rounded-none shadow-md"
            >
              {t('next')} →
            </button>
          </div>
        </div>

        {/* Input Form Below Slideshow */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <label className="text-[10px] text-[#888888] uppercase tracking-wider font-bold">
              {t('paste_ics_link')}
            </label>
          </div>

          <input
            type="url"
            placeholder="https://kingshigh.school.kiwi/ics/12345-XXXX.ics"
            value={urlInput}
            onChange={(e) => {
              setUrlInput(e.target.value);
              setLocalError(null);
            }}
            className="w-full bg-[#0e0e0e] border border-[#262626] focus:border-white text-white px-3.5 py-3 text-xs font-mono rounded-none outline-none transition-colors"
          />

          {(localError || error) && (
            <div className="text-xs text-[#ef4444] font-mono bg-red-950/20 p-2.5">
              {localError || error}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-[#222222] text-[#888888] hover:text-white text-xs uppercase font-bold rounded-none cursor-pointer"
            >
              {t('close')}
            </button>
            <button
              type="submit"
              disabled={saving || !urlInput.trim()}
              className="px-6 py-2.5 bg-white text-black hover:bg-[#e0e0e0] disabled:opacity-40 text-xs font-bold uppercase rounded-none transition-colors cursor-pointer"
            >
              {saving ? 'SAVING...' : t('save_timetable')}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

export default function TimetableWidget({ widget = {}, externalOpenSetup, onExternalCloseSetup }) {
  const { t } = useLanguage();
  const { getAccessTokenSilently } = useAuth0();

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 5000);
    return () => clearInterval(timer);
  }, []);

  const [icsUrl, setIcsUrl] = useState(() => localStorage.getItem('timetable_ics_url') || '');
  const [showSetupModal, setShowSetupModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showBreaks, setShowBreaks] = useState(() => localStorage.getItem('timetable_show_breaks') !== '0');
  const [layoutMode, setLayoutMode] = useState(() => localStorage.getItem('timetable_layout_mode') || 'current_next');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const [periods, setPeriods] = useState([]);
  const [loading, setLoading] = useState(false);

  // Sync with external modal triggers (from Onboarding modal)
  useEffect(() => {
    if (externalOpenSetup) {
      setShowSetupModal(true);
    }
  }, [externalOpenSetup]);

  const handleCloseModal = () => {
    setShowSetupModal(false);
    if (onExternalCloseSetup) onExternalCloseSetup();
  };

  // Auto-sync timetable ICS URL from server if not cached locally
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
          }
        }
      } catch { /* silent */ }
    };
    fetchSavedUrl();
  }, [icsUrl, getAccessTokenSilently]);

  // Fetch timetable data
  const fetchTimetable = useCallback(async (force = false) => {
    if (!icsUrl) return;
    setLoading(true);
    try {
      const today = new Date().toDateString();
      const cachedDate = localStorage.getItem('timetable_cache_date');
      const cachedData = localStorage.getItem('timetable_cache_data');
      if (!force && cachedDate === today && cachedData) {
        const cached = JSON.parse(cachedData);
        const list = Array.isArray(cached) ? cached : (cached.periods || cached.events || []);
        setPeriods(list);
        setLoading(false);
        return;
      }

      const token = await getAccessTokenSilently();
      const res = await fetch(`${API_URL}/api/timetable`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : (data.periods || data.events || []);
        setPeriods(list);
        localStorage.setItem('timetable_cache_date', today);
        localStorage.setItem('timetable_cache_data', JSON.stringify(data));
      }
    } catch { /* silent */ }
    finally {
      setLoading(false);
    }
  }, [icsUrl, getAccessTokenSilently]);

  useEffect(() => {
    fetchTimetable();
  }, [fetchTimetable]);

  const handleSaveUrl = async (trimmed) => {
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
      handleCloseModal();
      setShowSettings(false);
      fetchTimetable(true);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleUnlink = async () => {
    try {
      const token = await getAccessTokenSilently().catch(() => '');
      if (token) {
        await fetch(`${API_URL}/api/timetable/ics`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` }
        }).catch(() => {});
      }
    } catch { /* silent */ }
    localStorage.removeItem('timetable_ics_url');
    localStorage.removeItem('timetable_cache_date');
    localStorage.removeItem('timetable_cache_data');
    setIcsUrl('');
    setPeriods([]);
    setShowSettings(false);
  };

  // ── Timetable periods computation ──────────────────────────────────────────
  const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: 'Pacific/Auckland' });

  const activePeriodsList = periods.filter(p => {
    return p.date === todayStr || !p.date;
  });

  const processedPeriods = activePeriodsList.map(p => ({
    ...p,
    details: getPeriodDetails(p, now)
  }));

  const currentP = processedPeriods.find(p => p.details.isNow) ||
    processedPeriods.find(p => !p.details.isDone) ||
    processedPeriods[0];

  const nextP = processedPeriods.find(p => p !== currentP && !p.details.isDone);
  const nextSubject = nextP?.subject || nextP?.summary || null;
  const nextRoom = nextP?.room || nextP?.location || '--';
  const nextTime = nextP ? nextP.details.formattedStart : '--';

  const nowHour = now.getHours();
  const nowMin = now.getMinutes();
  const nowTotalMins = nowHour * 60 + nowMin;

  const isInterval = showBreaks && (nowTotalMins >= (10 * 60 + 30) && nowTotalMins < (10 * 60 + 55));
  const isLunch = showBreaks && (nowTotalMins >= (12 * 60 + 45) && nowTotalMins < (13 * 60 + 30));

  let activeEyebrow = t('current_class');
  let activeSubject = currentP?.subject || currentP?.summary || 'NO ACTIVE CLASS';
  let activeRoom = currentP?.room || currentP?.location || '--';
  let activeEnd = currentP ? currentP.details.formattedEnd : '--';
  let activeRemaining = currentP ? currentP.details.remainingMins : 0;

  if (isInterval) {
    activeEyebrow = t('interval');
    activeSubject = t('morning_interval');
    activeRoom = 'COURTYARD';
    activeEnd = '10:55am';
    activeRemaining = Math.max(0, (10 * 60 + 55) - nowTotalMins);
  } else if (isLunch) {
    activeEyebrow = t('lunch');
    activeSubject = t('lunch_break');
    activeRoom = 'COURTYARD';
    activeEnd = '1:30pm';
    activeRemaining = Math.max(0, (13 * 60 + 30) - nowTotalMins);
  }

  return (
    <section className="h-full flex flex-col p-5 select-none min-h-0 bg-[#000000] font-mono">
      {/* HEADER: Highly Obvious Button to Toggle Settings (Exact same style as Notices) */}
      <div className="flex items-center justify-between mb-3 pb-3 border-b border-[#222222] shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-white uppercase tracking-wider">
            {t('timetable')}
          </h2>
          {icsUrl && (
            <span className="text-xs text-[#888888]">
              ({processedPeriods.length} {t('periods')})
            </span>
          )}
        </div>

        {/* PROMINENT SETTINGS TOGGLE BUTTON - EXACT MATCH FOR NOTICES STYLE */}
        <button
          onClick={() => {
            if (!icsUrl) {
              setShowSetupModal(true);
            } else {
              setShowSettings(prev => !prev);
            }
          }}
          className={`px-3.5 py-1.5 border font-mono text-xs font-bold uppercase tracking-wider transition-all cursor-pointer rounded-none flex items-center gap-2 ${
            showSettings
              ? 'bg-white text-black border-white'
              : 'bg-[#141414] text-white border-[#333333] hover:border-white hover:bg-[#202020]'
          }`}
          title="Click to configure timetable display and settings"
        >
          <span className="material-symbols-outlined text-sm">tune</span>
          <span>{showSettings ? t('back_to_timetable') : t('timetable_settings')}</span>
        </button>
      </div>

      {/* BODY CONTENT: If no ICS URL is linked */}
      {!icsUrl ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          <h3 className="text-xl font-bold text-white mb-2 uppercase tracking-tight">
            {t('no_timetable')}
          </h3>
          <p className="text-xs text-[#888888] max-w-xs mb-8 uppercase tracking-wider">
            {t('link_kamar_prompt')}
          </p>
          <button
            onClick={() => setShowSetupModal(true)}
            className="px-8 py-4 bg-white hover:bg-[#e0e0e0] text-black font-mono text-sm font-bold uppercase tracking-wider rounded-none transition-all cursor-pointer"
          >
            {t('set_up_timetable')}
          </button>
        </div>
      ) : showSettings ? (
        /* TIMETABLE DISPLAY & FEED SETTINGS VIEW */
        <div className="flex-1 flex flex-col gap-5 overflow-y-auto custom-scrollbar pr-1">
          <div className="flex items-center justify-between pb-2 border-b border-[#1c1c1c]">
            <span className="text-xs font-bold uppercase tracking-wider text-white">
              {t('timetable_settings')}
            </span>
          </div>

          {/* Timetable Layout Selection */}
          <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
            <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase border-b border-[#1c1c1c] pb-2">
              TIMETABLE LAYOUT
            </span>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  setLayoutMode('current_next');
                  localStorage.setItem('timetable_layout_mode', 'current_next');
                }}
                className={`py-2 px-3 text-xs font-mono font-bold uppercase transition-all rounded-none cursor-pointer ${
                  layoutMode === 'current_next'
                    ? 'bg-white text-black'
                    : 'bg-[#141414] text-[#888888] hover:text-white border border-[#262626] hover:border-[#444444]'
                }`}
              >
                CURRENT &amp; NEXT (DEFAULT)
              </button>
              <button
                type="button"
                onClick={() => {
                  setLayoutMode('all_today');
                  localStorage.setItem('timetable_layout_mode', 'all_today');
                }}
                className={`py-2 px-3 text-xs font-mono font-bold uppercase transition-all rounded-none cursor-pointer ${
                  layoutMode === 'all_today'
                    ? 'bg-white text-black'
                    : 'bg-[#141414] text-[#888888] hover:text-white border border-[#262626] hover:border-[#444444]'
                }`}
              >
                ALL OF TODAY
              </button>
            </div>
          </div>

          {/* Display Feature Toggles */}
          <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
            <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase border-b border-[#1c1c1c] pb-2">
              {t('display_options')}
            </span>
            <div className="flex flex-col gap-2.5">
              <label className="flex items-center justify-between cursor-pointer py-1">
                <span className="text-xs text-white uppercase">{t('show_breaks')}</span>
                <input
                  type="checkbox"
                  checked={showBreaks}
                  onChange={(e) => {
                    setShowBreaks(e.target.checked);
                    localStorage.setItem('timetable_show_breaks', e.target.checked ? '1' : '0');
                  }}
                  className="accent-white w-4 h-4 cursor-pointer"
                />
              </label>
            </div>
          </div>

          {/* Calendar Feed Source & Actions */}
          <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2">
              <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase">
                {t('calendar_feed')}
              </span>
              <span className="text-[10px] font-mono text-emerald-400 uppercase font-bold">
                ✓ CONNECTED
              </span>
            </div>
            <div className="text-[11px] font-mono text-[#888888] truncate bg-[#060606] p-2 border border-[#1a1a1a]">
              {icsUrl}
            </div>
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                onClick={() => setShowSetupModal(true)}
                className="px-4 py-2 bg-white text-black hover:bg-[#e0e0e0] text-xs font-mono font-bold uppercase rounded-none transition-colors cursor-pointer"
              >
                {t('reconfigure_link')}
              </button>
              <button
                type="button"
                onClick={() => fetchTimetable(true)}
                className="px-4 py-2 bg-[#141414] border border-[#333333] hover:border-white text-white text-xs font-mono font-bold uppercase rounded-none transition-colors cursor-pointer"
              >
                {loading ? 'SYNCING...' : t('sync_timetable')}
              </button>
              <button
                type="button"
                onClick={handleUnlink}
                className="px-4 py-2 border border-[#441111] bg-red-950/20 hover:bg-red-900/30 text-red-400 text-xs font-mono font-bold uppercase rounded-none transition-colors cursor-pointer ml-auto"
              >
                {t('unlink_timetable')}
              </button>
            </div>
          </div>
        </div>
      ) : layoutMode === 'all_today' ? (
        /* ALL OF TODAY TIMETABLE LAYOUT */
        <div className="flex-1 flex flex-col gap-6 overflow-y-auto custom-scrollbar py-2 pr-1">
          {/* Previous periods of today: same styling as next, but crossed out & grey */}
          {processedPeriods.filter(p => p.details.isDone && p !== currentP).length > 0 && (
            <div className="flex flex-col gap-2.5">
              <span className="text-[10px] uppercase tracking-widest text-[#555555] font-bold">
                COMPLETED EARLIER TODAY
              </span>
              {processedPeriods.filter(p => p.details.isDone && p !== currentP).map((p, idx) => (
                <div
                  key={p.id || `prev-${idx}`}
                  className="border-t border-[#1c1c1c] pt-3 flex items-baseline gap-6 line-through text-[#555555] opacity-50 select-none"
                >
                  <span className="text-xs uppercase tracking-[2px] font-bold text-[#444444] w-16 shrink-0">
                    {p.details.formattedStart}
                  </span>
                  <div className="flex items-baseline gap-3">
                    <span className="text-base font-bold uppercase">
                      {p.subject || p.summary}
                    </span>
                    <span className="text-xs text-[#555555]">
                      {p.room || p.location || '--'} {p.details.formattedEnd !== '--' ? `· ended ${p.details.formattedEnd}` : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Current Period: Exact same hero styling */}
          <div className="flex flex-col gap-2 border-t border-[#222222] pt-4">
            <span className="text-xs uppercase tracking-[2px] font-bold text-[#888888]">
              {activeEyebrow}
            </span>
            <h1 className="text-[48px] md:text-[64px] font-bold text-white leading-none tracking-tight my-1 uppercase">
              {activeSubject}
            </h1>

            <div className="flex gap-8 md:gap-12 mt-2">
              <div className="flex flex-col">
                <span className="text-[11px] uppercase tracking-wider font-bold text-[#777777]">{t('room')}</span>
                <span className="text-[26px] font-bold text-white">{activeRoom}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] uppercase tracking-wider font-bold text-[#777777]">{t('ends')}</span>
                <span className="text-[26px] font-bold text-white">{activeEnd}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] uppercase tracking-wider font-bold text-[#777777]">{t('left')}</span>
                <span className={`text-[26px] font-bold ${activeRemaining <= 5 && activeRemaining > 0 ? 'text-[#ff4d4d]' : 'text-white'}`}>
                  {activeRemaining > 0 ? `${activeRemaining}m` : '--'}
                </span>
              </div>
            </div>
          </div>

          {/* Next and all subsequent periods of today */}
          {processedPeriods.filter(p => p !== currentP && !p.details.isDone).length > 0 && (
            <div className="flex flex-col gap-3 pt-2">
              {processedPeriods.filter(p => p !== currentP && !p.details.isDone).map((p, idx) => {
                const isImmediateNext = idx === 0;
                return (
                  <div key={p.id || `up-${idx}`} className="border-t border-[#1c1c1c] pt-3 flex items-baseline gap-6">
                    <span className={`text-xs uppercase tracking-[2px] font-bold ${isImmediateNext ? 'text-[#888888]' : 'text-[#555555]'} w-16 shrink-0`}>
                      {isImmediateNext ? t('next_class') : p.details.formattedStart}
                    </span>
                    <div className="flex items-baseline gap-3">
                      <span className="text-[22px] md:text-[26px] font-bold text-white uppercase">
                        {p.subject || p.summary}
                      </span>
                      <span className="text-[14px] text-[#888888]">
                        {p.room || p.location || '--'} {p.details.formattedStart !== '--' ? `· ${p.details.formattedStart}` : ''}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        /* NORMAL TIMETABLE HERO VIEW (CURRENT & NEXT) */
        <div className="flex-1 flex flex-col justify-center gap-8 py-4">
          {/* Current Period / Break Hero */}
          <div className="flex flex-col gap-2">
            <span className="text-xs uppercase tracking-[2px] font-bold text-[#888888]">
              {activeEyebrow}
            </span>
            <h1 className="text-[56px] md:text-[72px] font-bold text-white leading-none tracking-tight my-1 uppercase">
              {activeSubject}
            </h1>

            <div className="flex gap-8 md:gap-12 mt-3">
              <div className="flex flex-col">
                <span className="text-[11px] uppercase tracking-wider font-bold text-[#777777]">{t('room')}</span>
                <span className="text-[28px] font-bold text-white">{activeRoom}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] uppercase tracking-wider font-bold text-[#777777]">{t('ends')}</span>
                <span className="text-[28px] font-bold text-white">{activeEnd}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] uppercase tracking-wider font-bold text-[#777777]">{t('left')}</span>
                <span className={`text-[28px] font-bold ${activeRemaining <= 5 && activeRemaining > 0 ? 'text-[#ff4d4d]' : 'text-white'}`}>
                  {activeRemaining > 0 ? `${activeRemaining}m` : '--'}
                </span>
              </div>
            </div>
          </div>

          {/* Next Class Block */}
          {nextSubject && (
            <div className="border-t border-[#1c1c1c] pt-5 mt-2 flex items-baseline gap-6">
              <span className="text-xs uppercase tracking-[2px] font-bold text-[#888888] w-16 shrink-0">
                {t('next_class')}
              </span>
              <div className="flex items-baseline gap-3">
                <span className="text-[24px] md:text-[28px] font-bold text-white uppercase">
                  {nextSubject}
                </span>
                <span className="text-[14px] text-[#888888]">
                  {nextRoom} {nextTime !== '--' ? `· ${nextTime}` : ''}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      <TimetableSetupModal
        isOpen={showSetupModal}
        onClose={handleCloseModal}
        onSave={handleSaveUrl}
        saving={saving}
        error={saveError}
        currentUrl={icsUrl}
      />
    </section>
  );
}
