import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import './index.css'
import './styles/global.css'
import App from './App.jsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN || "your-tenant.auth0.com"
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID || "your-client-id"
const audience = import.meta.env.VITE_AUTH0_AUDIENCE || "smart-mirror-api"

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: audience
      }}
    >
      <App />
    </Auth0Provider>
  </StrictMode>,
)
