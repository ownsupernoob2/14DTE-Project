// ARCHIVED: the calendar-link (.ics) way of getting a timetable.
//
// Timetables now come from KAMAR through the server, using the student ID a
// student links in Settings, so nothing here is part of normal setup. It is
// kept as a fallback, tucked away at the bottom of Settings under
// "Troubleshooting", for when the KAMAR timetable isn't working for someone:
// they can paste their KAMAR portal calendar link instead and the server will
// read that. The server side (/api/timetable/ics) is unchanged.
//
// See docs/archive/ics-timetable-link.md.

import { useEffect, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { motion } from 'framer-motion';
import { useLanguage } from '../contexts/LanguageContext';
import step1Img from '../assets/timetable-instructions/1.png';
import step2Img from '../assets/timetable-instructions/2.png';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

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

// ── Slideshow for the setup modal: real screenshots of the KAMAR portal ──
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

// ── The tucked-away Settings section ─────────────────────────────────────────
// Closed by default and deliberately quiet: most students never need it. The
// current link is only fetched when it is first opened.
export default function LegacyCalendarLink({ disabled = false }) {
  const { getAccessTokenSilently } = useAuth0();
  const [loaded, setLoaded] = useState(false);
  const [icsUrl, setIcsUrl] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // The widget caches the week in the browser; drop it so a change shows up.
  const forgetCachedTimetable = () => {
    localStorage.removeItem('timetable_ics_url');
    localStorage.removeItem('timetable_cache_date');
    localStorage.removeItem('timetable_cache_data');
  };

  const load = async () => {
    try {
      const token = await getAccessTokenSilently();
      const res = await fetch(`${API_URL}/api/timetable/ics`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = res.ok ? await res.json() : {};
      setIcsUrl(data.ics_url || '');
    } catch { /* offline: show it as not linked */ }
    setLoaded(true);
  };

  const handleSave = async (url) => {
    setSaving(true);
    setError(null);
    try {
      const token = await getAccessTokenSilently();
      const res = await fetch(`${API_URL}/api/timetable/ics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ics_url: url }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Server error (${res.status})`);
      }
      forgetCachedTimetable();
      setIcsUrl(url);
      setShowModal(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleUnlink = async () => {
    try {
      const token = await getAccessTokenSilently();
      const res = await fetch(`${API_URL}/api/timetable/ics`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      forgetCachedTimetable();
      setIcsUrl('');
    } catch {
      alert('Could not remove the calendar link. Please try again.');
    }
  };

  return (
    <details
      className="px-1 text-[#444444]"
      onToggle={(e) => { if (e.currentTarget.open && !loaded) load(); }}
    >
      <summary className="cursor-pointer text-[10px] uppercase tracking-widest hover:text-[#888888] select-none">
        Troubleshooting
      </summary>

      <div className="mt-3 bg-[#0c0c0c] border border-[#1a1a1a] p-4 flex flex-col gap-3">
        <h3 className="text-[11px] font-bold uppercase tracking-widest text-[#888888]">
          Old timetable method: calendar link
        </h3>
        <p className="text-xs text-[#888888] leading-relaxed">
          Your timetable normally comes from KAMAR using the student ID linked above. If it isn&apos;t
          showing, or is wrong, you can paste the calendar link (.ics) from your KAMAR portal here
          instead. It is only used when KAMAR has no timetable for your student ID.
        </p>

        {icsUrl ? (
          <div className="text-[11px] text-[#888888] truncate bg-[#060606] p-2 border border-[#1a1a1a]">
            {icsUrl}
          </div>
        ) : (
          <span className="text-[11px] text-[#555555] uppercase">
            {loaded ? 'No calendar link saved' : 'Loading…'}
          </span>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setShowModal(true)}
            disabled={disabled || !loaded}
            className="px-4 py-2 bg-[#141414] border border-[#333333] hover:border-white text-white text-xs font-bold uppercase rounded-none transition-colors cursor-pointer disabled:opacity-50"
          >
            {icsUrl ? 'Change calendar link' : 'Add calendar link'}
          </button>
          {icsUrl && (
            <button
              type="button"
              onClick={handleUnlink}
              disabled={disabled}
              className="px-4 py-2 border border-[#441111] bg-red-950/20 hover:bg-red-900/30 text-red-400 text-xs font-bold uppercase rounded-none transition-colors cursor-pointer disabled:opacity-50"
            >
              Remove link
            </button>
          )}
        </div>
      </div>

      <TimetableSetupModal
        isOpen={showModal}
        onClose={() => { setShowModal(false); setError(null); }}
        onSave={handleSave}
        saving={saving}
        error={error}
        currentUrl={icsUrl}
      />
    </details>
  );
}
