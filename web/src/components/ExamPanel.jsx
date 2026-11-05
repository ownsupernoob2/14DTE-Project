import { useCallback, useEffect, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';
const TZ = 'Pacific/Auckland';

const inputClass =
  'w-full bg-[#0c0c0c] border border-[#333333] focus:border-white outline-none text-white text-sm font-mono px-3 py-2 rounded-none';
const labelClass = 'text-[10px] uppercase tracking-widest font-bold text-[#888888]';

function todayStr() {
  return new Date().toLocaleDateString('en-CA', { timeZone: TZ });
}

/** Whole days from today (NZ) to a YYYY-MM-DD date. */
function daysUntil(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const [ty, tm, td] = todayStr().split('-').map(Number);
  return Math.round((Date.UTC(y, m - 1, d) - Date.UTC(ty, tm - 1, td)) / 86400000);
}

function whenLabel(dateStr) {
  const n = daysUntil(dateStr);
  if (n === 0) return 'TODAY';
  if (n === 1) return 'TOMORROW';
  return `IN ${n} DAYS`;
}

function dateParts(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const day = new Date(Date.UTC(y, m - 1, d));
  return {
    weekday: day.toLocaleDateString('en-NZ', { weekday: 'short', timeZone: 'UTC' }),
    date: day.toLocaleDateString('en-NZ', { day: 'numeric', month: 'short', timeZone: 'UTC' }),
  };
}

function time12h(hhmm) {
  if (!hhmm) return 'TIME TBC';
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')}${h >= 12 ? 'pm' : 'am'}`;
}

function lengthLabel(mins) {
  if (!mins) return '';
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h ? `${h}h` : ''}${m ? ` ${m}m` : ''}`.trim();
}

const emptyForm = { subject: '', date: '', startTime: '', durationMin: '', room: '' };

/**
 * Shown where the timetable says NO ACTIVE CLASS: the student's exams, soonest
 * first, and a form to type more in. They show on the mirror too.
 */
export default function ExamPanel({ noClass = false }) {
  const { getAccessTokenSilently } = useAuth0();
  const [exams, setExams] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const authed = useCallback(async (path, options = {}) => {
    const token = await getAccessTokenSilently();
    return fetch(`${API_URL}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    });
  }, [getAccessTokenSilently]);

  const load = useCallback(async () => {
    try {
      const res = await authed('/api/exams');
      if (res.ok) setExams((await res.json()).exams || []);
    } catch { /* leave the list as it was */ }
    setLoaded(true);
  }, [authed]);

  useEffect(() => { load(); }, [load]);

  const upcoming = exams.filter((e) => e.date >= todayStr());
  const groups = [];
  for (const exam of upcoming) {
    const last = groups[groups.length - 1];
    if (last && last.date === exam.date) last.items.push(exam);
    else groups.push({ date: exam.date, items: [exam] });
  }

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const res = await authed('/api/exams', {
        method: 'POST',
        body: JSON.stringify({
          subject: form.subject,
          date: form.date,
          startTime: form.startTime,
          durationMin: form.durationMin ? parseInt(form.durationMin, 10) : 0,
          room: form.room,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || 'Could not save the exam.');
      } else {
        setForm(emptyForm);
        setAdding(false);
        await load();
      }
    } catch {
      setError('Could not reach the server. Try again.');
    }
    setSaving(false);
  };

  const remove = async (id) => {
    setExams((list) => list.filter((x) => x.id !== id));
    try {
      await authed(`/api/exams/${id}`, { method: 'DELETE' });
    } catch { /* the reload below puts it back if it didn't go */ }
    load();
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 py-2">
      <div className="flex items-end justify-between gap-4 pb-4 border-b border-[#222222] shrink-0">
        <div>
          <span className="text-xs uppercase tracking-[2px] font-bold text-[#888888]">
            {noClass ? 'No active class' : 'Exam timetable'}
          </span>
          <h1 className="text-[32px] md:text-[40px] font-bold text-white leading-none tracking-tight mt-1 uppercase">
            Your exams
          </h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
        <a
          href="/2026-Exam-Timetable.pdf"
          target="_blank"
          rel="noopener noreferrer"
          className="px-4 py-2 border bg-[#141414] text-white border-[#333333] hover:border-white font-mono text-xs font-bold uppercase tracking-wider cursor-pointer rounded-none"
        >
          Exam timetable (PDF)
        </a>
        <button
          type="button"
          onClick={() => { setAdding((v) => !v); setError(''); }}
          className={`px-4 py-2 border font-mono text-xs font-bold uppercase tracking-wider cursor-pointer rounded-none ${
            adding ? 'bg-white text-black border-white' : 'bg-[#141414] text-white border-[#333333] hover:border-white'
          }`}
        >
          {adding ? 'Cancel' : '+ Add exam'}
        </button>
        </div>
      </div>

      {adding && (
        <form onSubmit={save} className="grid grid-cols-2 gap-3 py-4 border-b border-[#1c1c1c] shrink-0">
          <label className="col-span-2 flex flex-col gap-1">
            <span className={labelClass}>Subject</span>
            <input className={inputClass} value={form.subject} onChange={set('subject')} maxLength={60}
              placeholder="e.g. Calculus" required autoFocus />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Date</span>
            <input className={inputClass} type="date" value={form.date} onChange={set('date')} required
              min={`${todayStr().slice(0, 4)}-11-01`} max={`${todayStr().slice(0, 4)}-12-09`} />
            <span className="text-[10px] text-[#666666] uppercase tracking-wider">1 Nov to 9 Dec</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Start time (optional)</span>
            <input className={inputClass} type="time" value={form.startTime} onChange={set('startTime')} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Room (optional)</span>
            <input className={inputClass} value={form.room} onChange={set('room')} maxLength={24} placeholder="e.g. Hall" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Length in minutes (optional)</span>
            <input className={inputClass} type="number" min="0" max="600" step="5" value={form.durationMin}
              onChange={set('durationMin')} placeholder="e.g. 180" />
          </label>
          {error && <p className="col-span-2 text-xs text-[#ff4d4d] font-mono">{error}</p>}
          <div className="col-span-2 flex justify-end">
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2 bg-white text-black font-mono text-xs font-bold uppercase tracking-wider rounded-none cursor-pointer disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save exam'}
            </button>
          </div>
        </form>
      )}

      <div className="flex-1 overflow-y-auto custom-scrollbar pt-4 pr-1 min-h-0">
        {loaded && groups.length === 0 && !adding && (
          <p className="text-xs text-[#888888] uppercase tracking-wider leading-relaxed max-w-md">
            {noClass ? 'No classes right now. ' : ''}Type in your exam timetable (1 Nov to 9 Dec) and it shows here and on the mirror.
          </p>
        )}
        {groups.map((g) => {
          const { weekday, date } = dateParts(g.date);
          return (
            <div key={g.date} className="flex gap-5 border-b border-[#1c1c1c] py-3">
              <div className="w-20 shrink-0">
                <div className="text-[11px] font-bold uppercase tracking-widest text-[#38bdf8]">{weekday}</div>
                <div className="text-lg font-bold text-white uppercase">{date}</div>
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#777777] mt-0.5">{whenLabel(g.date)}</div>
              </div>
              <div className="flex-1 flex flex-col gap-2.5 min-w-0">
                {g.items.map((x) => (
                  <div key={x.id} className="flex items-baseline gap-4">
                    <span className="w-20 shrink-0 text-xs font-bold uppercase tracking-wider text-[#cbd5e1]">
                      {time12h(x.startTime)}
                    </span>
                    <span className="flex-1 min-w-0 truncate text-[20px] font-bold text-white uppercase">{x.subject}</span>
                    <span className="text-xs text-[#888888] uppercase shrink-0">
                      {[x.room, lengthLabel(x.durationMin)].filter(Boolean).join(' · ')}
                    </span>
                    <button
                      type="button"
                      onClick={() => remove(x.id)}
                      className="text-[#666666] hover:text-[#ff4d4d] text-lg leading-none cursor-pointer shrink-0"
                      title="Delete this exam"
                      aria-label={`Delete ${x.subject}`}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
