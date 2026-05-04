import { useAuth0 } from '@auth0/auth0-react'
import { motion } from 'framer-motion'

export default function Login() {
  const { loginWithRedirect } = useAuth0()

  return (
    <div className="flex min-h-screen items-center justify-center bg-black px-6 text-white">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md rounded-3xl border border-white/10 bg-mirror-gray/90 p-8 shadow-soft"
      >
        <p className="text-xs uppercase tracking-[0.4em] text-white/50">Smart Mirror</p>
        <h1 className="mt-4 text-3xl font-semibold">Welcome back</h1>
        <p className="mt-2 text-sm text-white/70">Sign in to access your dashboard.</p>

        <div className="mt-8 space-y-3">
          <button
            onClick={() => loginWithRedirect()}
            className="w-full rounded-full border border-white bg-white py-3 text-sm font-semibold uppercase tracking-[0.35em] text-black"
          >
            Continue with Email
          </button>
          <button
            onClick={() => loginWithRedirect({ authorizationParams: { connection: 'google-oauth2' } })}
            className="w-full rounded-full border border-white/40 bg-transparent py-3 text-sm font-semibold uppercase tracking-[0.35em] text-white"
          >
            Continue with Google
          </button>
        </div>

        <p className="mt-6 text-xs text-white/60">
          Don&apos;t have an account?{' '}
          <span
            className="cursor-pointer text-white underline"
            onClick={() => loginWithRedirect({ authorizationParams: { screen_hint: 'signup' } })}
          >
            Register here
          </span>
        </p>
      </motion.div>
    </div>
  )
}
