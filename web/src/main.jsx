import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import './index.css'
import './App.css'
import App from './App.jsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN || "dev-pgz1qjberxzo8hkl.us.auth0.com"
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID || "TWViWK6pUo2YmjO4CCqUNCdJYRy8eTqZ"
const audience = import.meta.env.VITE_AUTH0_AUDIENCE || "https://dev-pgz1qjberxzo8hkl.us.auth0.com/api/v2/"

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      cacheLocation="localstorage"
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: audience
      }}
    >
      <App />
    </Auth0Provider>
  </StrictMode>,
)
