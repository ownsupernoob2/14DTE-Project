import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../contexts/LanguageContext'
import DailyNoticesWidget from '../components/DailyNoticesWidget'
import MirrorNoticeBar from '../components/MirrorNoticeBar'

// Signed-out home: today's notices on the left (anyone may read them), and
// signing in on the right where the timetable goes once you have an account.
export default function Login() {
  const { loginWithRedirect, error } = useAuth0()
  const { t } = useLanguage()

  return (
    <div className="h-screen w-full flex flex-col bg-[#000000] text-white font-sans overflow-hidden">
      <header className="bg-[#000000] border-b border-[#1c1c1c] flex justify-between items-center w-full px-6 h-14 shrink-0 select-none">
        <span className="text-sm font-mono font-bold uppercase tracking-wider text-white">{t('brand')}</span>
        <button
          onClick={() => loginWithRedirect()}
          className="px-3 py-1.5 border font-mono text-xs font-bold uppercase tracking-wider rounded-none bg-[#000000] text-[#888888] border-[#222222] hover:text-white hover:border-[#444444] transition-colors cursor-pointer"
        >
          Sign in
        </button>
      </header>

      <MirrorNoticeBar />

      <main className="grid grid-cols-1 md:grid-cols-[48%_52%] flex-1 min-h-0 overflow-hidden">
        {/* LEFT: today's notices */}
        <section className="flex flex-col h-full min-h-0 bg-[#000000] border-r border-[#1c1c1c]">
          <DailyNoticesWidget widget={{}} />
        </section>

        {/* RIGHT: sign in */}
        <section className="flex flex-col p-6 md:p-8 h-full min-h-0 bg-[#000000] overflow-y-auto font-mono select-none">
          <div className="flex-1 flex items-center justify-center py-6">
            <div className="bg-[#0c0c0c] border border-[#222222] p-8 max-w-md w-full text-center flex flex-col gap-6 rounded-none">
              <div>
                <h1 className="text-xl font-bold uppercase tracking-wider text-white">
                  {t('brand')}
                </h1>
                <p className="text-xs text-[#888888] mt-1 uppercase tracking-wider">
                  STUDENT PORTAL AUTHENTICATION
                </p>
              </div>

              <p className="text-xs text-[#aaaaaa] leading-relaxed">
                Sign in to see your timetable, link your student ID and set up the mirror for you.
              </p>

              {error && (
                <div className="text-xs text-[#ef4444] bg-red-950/20 p-3 text-left">
                  <p className="font-bold">LOGIN ERROR:</p>
                  <p>{error.message}</p>
                </div>
              )}

              <button
                onClick={() => loginWithRedirect()}
                className="w-full py-3 bg-white hover:bg-[#e0e0e0] text-black font-mono text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer rounded-none"
              >
                SIGN IN / REGISTER
              </button>

              <div className="pt-4 border-t border-[#1c1c1c] flex flex-col gap-2">
                <p className="text-[11px] text-[#777777] leading-relaxed">
                  By signing up or logging in, you agree to our{' '}
                  <Link to="/privacy" className="text-white underline hover:text-[#cccccc]">
                    {t('privacy')}
                  </Link>{' '}
                  and{' '}
                  <Link to="/terms" className="text-white underline hover:text-[#cccccc]">
                    {t('terms')}
                  </Link>.
                </p>
                <p className="text-[10px] text-[#555555] italic">
                  &quot;Using the mirror and personalising it by signing up is entirely optional.&quot;
                </p>
              </div>
            </div>
          </div>

          <div className="pt-3 border-t border-[#1c1c1c] flex items-center justify-between text-[11px] font-mono text-[#666666] shrink-0">
            <div className="flex items-center gap-3">
              <Link to="/privacy" className="hover:text-white transition-colors">{t('privacy')}</Link>
              <span>·</span>
              <Link to="/terms" className="hover:text-white transition-colors">{t('terms')}</Link>
            </div>
            <div className="text-[10px] text-[#888888] uppercase tracking-wider">KING&apos;S HIGH SCHOOL SMART MIRROR</div>
          </div>
        </section>
      </main>
    </div>
  )
}
