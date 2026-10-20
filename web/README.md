# Smart Mirror — website

React + Vite site where students sign in (Auth0), register their face or student ID, link their timetable and arrange their mirror. Administrators get `/admin`: analytics and A/B testing, the users table, and the mirror screensaver.

## Run locally

```bash
npm install
npm run dev
```

Settings come from `.env` (all public, browser-side values):

| Variable | |
|---|---|
| `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE` | Auth0 application |
| `VITE_API_URL` | Server, e.g. `https://api.smartmirror.me` |

## Deploy

`npm run build` produces `dist/`; Vercel builds it on every push (`vercel.json` routes all paths to the single-page app).

Who is an administrator is decided by the server (`ADMIN_EMAILS`), not by the site.
