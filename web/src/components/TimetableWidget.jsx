import { useEffect, useState, useCallback } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { useLanguage } from '../contexts/LanguageContext';

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

export default function TimetableWidget({ widget = {} }) {
  const { t } = useLanguage();
  const { getAccessTokenSilently, user } = useAuth0();

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 5000);
    return () => clearInterval(timer);
  }, []);

  const [showSettings, setShowSettings] = useState(false);
  const [showBreaks, setShowBreaks] = useState(() => localStorage.getItem('timetable_show_breaks') !== '0');
  const [layoutMode, setLayoutMode] = useState(() => localStorage.getItem('timetable_layout_mode') || 'current_next');

  const [periods, setPeriods] = useState([]);
  const [loading, setLoading] = useState(false);
  // Set when the server has no timetable for this student (no ID linked, or
  // KAMAR hasn't sent theirs): say how to fix it rather than show nothing.
  const [noTimetable, setNoTimetable] = useState(false);
  const cacheOwner = user?.sub || '';

  // The timetable comes from KAMAR through the server, using the student ID
  // linked in Settings. (The old calendar-link method is archived under
  // Settings > Troubleshooting.)
  const fetchTimetable = useCallback(async (force = false) => {
    setLoading(true);
    try {
      const today = new Date().toDateString();
      const cachedDate = localStorage.getItem('timetable_cache_date');
      const cachedData = localStorage.getItem('timetable_cache_data');
      // The cached week is only good for the same person on the same day.
      const cachedFor = localStorage.getItem('timetable_cache_user');
      if (!force && cachedDate === today && cachedData && cachedFor === cacheOwner) {
        const cached = JSON.parse(cachedData);
        const list = Array.isArray(cached) ? cached : (cached.periods || cached.events || []);
        setPeriods(list);
        setNoTimetable(false);
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
        setNoTimetable(false);
        localStorage.setItem('timetable_cache_date', today);
        localStorage.setItem('timetable_cache_data', JSON.stringify(data));
        localStorage.setItem('timetable_cache_user', cacheOwner);
      } else if (res.status === 404) {
        setPeriods([]);
        setNoTimetable(true);
        localStorage.removeItem('timetable_cache_date');
        localStorage.removeItem('timetable_cache_data');
      }
    } catch { /* silent */ }
    finally {
      setLoading(false);
    }
  }, [cacheOwner, getAccessTokenSilently]);

  useEffect(() => {
    fetchTimetable();
  }, [fetchTimetable]);

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
          {!noTimetable && (
            <span className="text-xs text-[#888888]">
              ({processedPeriods.length} {t('periods')})
            </span>
          )}
        </div>

        {/* PROMINENT SETTINGS TOGGLE BUTTON - EXACT MATCH FOR NOTICES STYLE */}
        <button
          onClick={() => setShowSettings(prev => !prev)}
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

      {/* BODY CONTENT: the server has no timetable for this student */}
      {noTimetable && !showSettings ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          <h3 className="text-xl font-bold text-white mb-2 uppercase tracking-tight">
            {t('no_timetable_yet')}
          </h3>
          <p className="text-xs text-[#888888] max-w-xs mb-8 uppercase tracking-wider">
            {t('timetable_from_kamar')}
          </p>
          <a
            href="/settings"
            className="px-8 py-4 bg-white hover:bg-[#e0e0e0] text-black font-mono text-sm font-bold uppercase tracking-wider rounded-none transition-all cursor-pointer"
          >
            {t('open_settings')}
          </a>
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

          {/* Where the timetable comes from, and a manual refresh */}
          <div className="bg-[#0c0c0c] p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-[#1c1c1c] pb-2">
              <span className="text-[11px] font-bold tracking-widest text-[#888888] uppercase">
                {t('timetable_source')}
              </span>
              <span className={`text-[10px] font-mono uppercase font-bold ${noTimetable ? 'text-amber-400' : 'text-emerald-400'}`}>
                {noTimetable ? t('no_timetable_yet') : `✓ ${t('timetable_kamar')}`}
              </span>
            </div>
            <p className="text-[11px] text-[#888888] leading-relaxed">
              {t('timetable_from_kamar')}
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                onClick={() => fetchTimetable(true)}
                className="px-4 py-2 bg-[#141414] border border-[#333333] hover:border-white text-white text-xs font-mono font-bold uppercase rounded-none transition-colors cursor-pointer"
              >
                {loading ? 'SYNCING...' : t('sync_timetable')}
              </button>
              <a
                href="/settings"
                className="px-4 py-2 bg-[#141414] border border-[#333333] hover:border-white text-white text-xs font-mono font-bold uppercase rounded-none transition-colors cursor-pointer"
              >
                {t('open_settings')}
              </a>
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

    </section>
  );
}
