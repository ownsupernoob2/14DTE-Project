import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../contexts/LanguageContext'

export default function Login() {
  const { loginWithRedirect, error } = useAuth0()
  const { t } = useLanguage()

  return (
    <div className="min-h-screen bg-[#000000] text-white flex items-center justify-center p-4 font-mono select-none">
      <div className="bg-[#0c0c0c] border border-[#222222] p-8 max-w-md w-full text-center flex flex-col gap-6 rounded-none">
        <div>
          <h1 className="text-xl font-bold uppercase tracking-wider text-white">
            {t('brand')}
          </h1>
          <p className="text-xs text-[#888888] mt-1 uppercase tracking-wider">
            STUDENT PORTAL AUTHENTICATION
          </p>
        </div>

        {error && (
          <div className="text-xs text-[#ef4444] bg-red-950/20 p-3 text-left">
            <p className="font-bold">LOGIN ERROR:</p>
            <p>{error.message}</p>
          </div>
        )}

        <div>
          <button
            onClick={() => loginWithRedirect()}
            className="w-full py-3 bg-white hover:bg-[#e0e0e0] text-black font-mono text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer rounded-none"
          >
            SIGN IN / REGISTER
          </button>
        </div>

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
            "Using the mirror and personalising it by signing up is entirely optional."
          </p>
        </div>
      </div>
    </div>
  )
}
