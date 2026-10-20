/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { API_URL, CONTACT_EMAIL } from '../config'

// The signed-in user as the server sees them: whether they are an admin (the
// server decides, from their verified Auth0 email) and any messages waiting for
// them, such as "your face scan was removed".
const MeContext = createContext({
  me: null,
  meChecked: false,
  isAdmin: false,
  messages: [],
  contactEmail: CONTACT_EMAIL,
  refresh: () => {},
  dismissMessages: () => {},
  authFetch: () => Promise.reject(new Error('not signed in')),
})

export function MeProvider({ children }) {
  const { isAuthenticated, getAccessTokenSilently } = useAuth0()
  const [me, setMe] = useState(null)
  const [checked, setChecked] = useState(false) // asked the server at least once

  const authFetch = useCallback(async (path, options = {}) => {
    const token = await getAccessTokenSilently()
    const headers = { ...(options.headers || {}), Authorization: `Bearer ${token}` }
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json'
    }
    return fetch(`${API_URL}${path}`, { ...options, headers })
  }, [getAccessTokenSilently])

  const fetchMe = useCallback(async () => {
    const res = await authFetch('/api/users/me')
    return res.ok ? res.json() : null
  }, [authFetch])

  const refresh = useCallback(async () => {
    try {
      const fresh = await fetchMe()
      if (fresh) setMe(fresh)
    } catch {
      /* server offline: keep what we had */
    }
  }, [fetchMe])

  useEffect(() => {
    if (!isAuthenticated) return undefined
    let cancelled = false
    fetchMe()
      .then((fresh) => { if (fresh && !cancelled) setMe(fresh) })
      .catch(() => { /* server offline */ })
      .finally(() => { if (!cancelled) setChecked(true) })
    return () => { cancelled = true }
  }, [isAuthenticated, fetchMe])

  const current = isAuthenticated ? me : null

  const dismissMessages = useCallback(async () => {
    setMe((prev) => (prev ? { ...prev, messages: [] } : prev))
    try {
      await authFetch('/api/users/me/messages/seen', { method: 'POST' })
    } catch {
      /* shown again next time */
    }
  }, [authFetch])

  return (
    <MeContext.Provider
      value={{
        me: current,
        meChecked: checked,
        isAdmin: Boolean(current?.is_admin),
        messages: current?.messages || [],
        contactEmail: current?.contact_email || CONTACT_EMAIL,
        refresh,
        dismissMessages,
        authFetch,
      }}
    >
      {children}
    </MeContext.Provider>
  )
}

export function useMe() {
  return useContext(MeContext)
}
