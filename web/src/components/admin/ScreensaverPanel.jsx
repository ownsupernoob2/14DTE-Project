import { useCallback, useEffect, useRef, useState } from 'react'
import { useMe } from '../../contexts/MeContext'
import { API_URL } from '../../config'

const MODES = [
  { id: 'demo', label: 'Gesture Demo', sub: 'Loops the how-to video', icon: 'smart_display' },
  { id: 'slideshow', label: 'Slideshow', sub: 'Your images, in turn', icon: 'photo_library' },
  { id: 'logo', label: 'Logo', sub: 'One image, centred', icon: 'image' },
]
const MAX_SLIDES = 40

export default function ScreensaverPanel() {
  const { authFetch } = useMe()
  const [cfg, setCfg] = useState(null)
  const [seconds, setSeconds] = useState(8)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  const slideInput = useRef(null)
  const logoInput = useRef(null)

  const show = (msg) => {
    setFeedback(msg)
    setTimeout(() => setFeedback(''), 6000)
  }

  const apply = (json) => {
    setCfg(json)
    setSeconds(json.slide_seconds || 8)
  }

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/screensaver`)
      apply(await res.json())
    } catch {
      show('Error: could not load the screensaver settings')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetch(`${API_URL}/api/screensaver`)
      .then((res) => res.json())
      .then((json) => { if (!cancelled) apply(json) })
      .catch(() => { if (!cancelled) show('Error: could not load the screensaver settings') })
    return () => { cancelled = true }
  }, [])

  const save = async (patch) => {
    setBusy(true)
    try {
      const res = await authFetch('/api/admin/screensaver', { method: 'POST', body: JSON.stringify(patch) })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
      setCfg(body)
      setSeconds(body.slide_seconds)
      show('Saved. Mirrors pick this up within a minute.')
    } catch (e) {
      show(`Error: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  const upload = async (kind, files) => {
    if (!files?.length) return
    setBusy(true)
    try {
      const form = new FormData()
      for (const f of files) form.append('files', f)
      const res = await authFetch(`/api/admin/screensaver/images?kind=${kind}`, { method: 'POST', body: form })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
      show(body.rejected?.length ? `Uploaded, but skipped: ${body.rejected.join(', ')}` : 'Uploaded.')
      await load()
    } catch (e) {
      show(`Error: ${e.message}`)
    } finally {
      setBusy(false)
      if (slideInput.current) slideInput.current.value = ''
      if (logoInput.current) logoInput.current.value = ''
    }
  }

  const remove = async (img) => {
    if (!window.confirm('Remove this image from the screensaver?')) return
    setBusy(true)
    try {
      const res = await authFetch(`/api/admin/screensaver/images/${img.id}`, { method: 'DELETE' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
      setCfg(body)
      show(body.mode === 'demo' && cfg?.mode !== 'demo' ? 'Removed. Nothing left to show, so mirrors went back to the gesture demo.' : 'Removed.')
    } catch (e) {
      show(`Error: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  if (!cfg) {
    return <div className="py-12 text-center text-[#666666] text-xs uppercase tracking-widest">Loading screensaver…</div>
  }

  const slides = cfg.slides || []
  const canUse = { demo: true, slideshow: slides.length > 0, logo: Boolean(cfg.logo) }

  return (
    <section className="flex flex-col gap-6">
      <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="material-symbols-outlined text-white text-lg">wallpaper</span>
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Mirror Screensaver</h3>
            <p className="text-xs text-[#888888] mt-0.5 uppercase tracking-wider">
              Shown full screen while nobody is at the mirror. Mirrors cache it and keep it while offline.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {MODES.map((m) => {
            const active = cfg.mode === m.id
            return (
              <button
                key={m.id}
                onClick={() => save({ mode: m.id })}
                disabled={busy || active || !canUse[m.id]}
                title={canUse[m.id] ? '' : `Upload ${m.id === 'logo' ? 'a logo' : 'images'} first`}
                className={`p-3 text-left rounded-none border transition-all cursor-pointer disabled:cursor-default ${
                  active ? 'bg-white text-black border-white' : 'bg-[#121212] hover:bg-[#1a1a1a] text-white border-[#262626]'
                } ${!canUse[m.id] && !active ? 'opacity-40' : ''}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="material-symbols-outlined text-base">{m.icon}</span>
                  {active && <span className="text-[9px] font-bold tracking-widest uppercase bg-black text-white px-1.5">ACTIVE</span>}
                </div>
                <div className="text-[11px] font-bold tracking-wider uppercase">{m.label}</div>
                <div className={`text-[10px] mt-0.5 ${active ? 'text-[#333333]' : 'text-[#777777]'}`}>{m.sub}</div>
              </button>
            )
          })}
        </div>

        {feedback && (
          <div className={`mt-4 text-xs font-mono flex items-center gap-1.5 ${feedback.startsWith('Error') ? 'text-red-400' : 'text-[#22c55e]'}`}>
            <span className="material-symbols-outlined text-sm">{feedback.startsWith('Error') ? 'error' : 'check_circle'}</span>
            {feedback}
          </div>
        )}
      </div>

      {/* Slideshow */}
      <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-5">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span className="material-symbols-outlined text-white text-lg">photo_library</span>
              Slideshow Images
            </h3>
            <p className="text-xs text-[#888888] mt-0.5 uppercase tracking-wider">
              JPEG, PNG or WebP, up to 10 MB each · {slides.length}/{MAX_SLIDES}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-[11px] text-[#888888] uppercase">
              Seconds each
              <input
                type="number" min={3} max={120} value={seconds}
                onChange={(e) => setSeconds(e.target.value)}
                onBlur={() => Number(seconds) !== cfg.slide_seconds && save({ slide_seconds: Number(seconds) })}
                className="w-16 bg-[#121212] border border-[#333333] px-2 py-1.5 text-white text-xs font-mono"
              />
            </label>
            <input ref={slideInput} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
              onChange={(e) => upload('slide', e.target.files)} />
            <button onClick={() => slideInput.current?.click()} disabled={busy || slides.length >= MAX_SLIDES}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold uppercase bg-white text-black hover:bg-[#e0e0e0] cursor-pointer disabled:opacity-50">
              <span className="material-symbols-outlined text-base">upload</span>
              Add images
            </button>
          </div>
        </div>

        {slides.length === 0 ? (
          <div className="py-10 text-center text-[#666666] font-mono text-xs border border-dashed border-[#222222] bg-[#0a0a0a]">
            No slideshow images yet.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {slides.map((img, i) => (
              <div key={img.id} className="relative group border border-[#222222] bg-black aspect-video">
                <img src={`${API_URL}${img.url}`} alt={`Slide ${i + 1}`} className="w-full h-full object-contain" loading="lazy" />
                <span className="absolute top-1 left-1 text-[10px] bg-black/80 text-white px-1.5 font-mono">{i + 1}</span>
                <button onClick={() => remove(img)} disabled={busy} aria-label={`Remove slide ${i + 1}`}
                  className="absolute top-1 right-1 bg-black/80 text-white hover:text-red-400 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity cursor-pointer p-0.5">
                  <span className="material-symbols-outlined text-base">delete</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Logo */}
      <div className="bg-[#0c0c0c] border border-[#222222] rounded-none p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-5">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span className="material-symbols-outlined text-white text-lg">image</span>
              Logo
            </h3>
            <p className="text-xs text-[#888888] mt-0.5 uppercase tracking-wider">
              Shown centred on black. A transparent PNG looks best.
            </p>
          </div>
          <div className="flex gap-2">
            <input ref={logoInput} type="file" accept="image/jpeg,image/png,image/webp" hidden
              onChange={(e) => upload('logo', e.target.files)} />
            <button onClick={() => logoInput.current?.click()} disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold uppercase bg-white text-black hover:bg-[#e0e0e0] cursor-pointer disabled:opacity-50">
              <span className="material-symbols-outlined text-base">upload</span>
              {cfg.logo ? 'Replace logo' : 'Upload logo'}
            </button>
            {cfg.logo && (
              <button onClick={() => remove(cfg.logo)} disabled={busy}
                className="px-4 py-2 text-xs font-bold uppercase border border-[#333333] text-white hover:border-white cursor-pointer disabled:opacity-50">
                Remove
              </button>
            )}
          </div>
        </div>
        <div className="bg-black border border-[#222222] h-48 flex items-center justify-center">
          {cfg.logo ? (
            <img src={`${API_URL}${cfg.logo.url}`} alt="Screensaver logo" className="max-h-40 max-w-[80%] object-contain" />
          ) : (
            <span className="text-[#555555] text-xs font-mono">No logo uploaded</span>
          )}
        </div>
      </div>
    </section>
  )
}
