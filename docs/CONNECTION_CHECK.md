# Backend–Frontend Connection Check

## Overview

- **Frontend** (Vercel): `https://frontend-rho-eight-72.vercel.app`
- **Backend** (Render): Set via `NEXT_PUBLIC_API_URL`; default in code: `https://mh5-backend.onrender.com`

All frontend API calls use `NEXT_PUBLIC_API_URL` (or the default above). CORS is configured on the backend to allow the frontend origin.

---

## 1. Frontend → Backend URL

| Where              | Source of backend URL |
|--------------------|------------------------|
| REST (login, API)  | `lib/api.ts` → `NEXT_PUBLIC_API_URL` or `DEFAULT_PUBLIC_API_URL` from `lib/config.ts` |
| GraphQL (Apollo)  | `lib/apollo-client.ts`, `apollo-provider.tsx` → same env/default |
| Share rewrites     | `next.config.js` → same env, same default string |
| Other fetch calls  | Various files → `NEXT_PUBLIC_API_URL` or `http://localhost:8000` (dev) |

**Single default:** `lib/config.ts` exports `DEFAULT_PUBLIC_API_URL = 'https://mh5-backend.onrender.com'`.  
If your Render service has a **different** URL (e.g. `https://mh5-backend-xxxx.onrender.com`), you **must** set it in Vercel:

- **Vercel** → Project → **Settings** → **Environment Variables**
- Add: `NEXT_PUBLIC_API_URL` = `https://<your-render-service>.onrender.com` (no trailing slash)
- Redeploy the frontend so the value is applied.

---

## 2. Backend CORS (who can call the API)

Backend allows requests from:

- **Hardcoded in `backend/main.py`:**  
  `localhost:3000`, `localhost:8000`, `127.0.0.1:3000/8000`,  
  `myhigh5.com`, `www.myhigh5.com`,  
  `mh5-hbjp.onrender.com`,  
  `https://frontend-rho-eight-72.vercel.app`
- **From env:** `BACKEND_CORS_ORIGINS` (in Render: `https://frontend-rho-eight-72.vercel.app`)
- **Regex:** Any `https://*.vercel.app` and `https://*.vercel.dev`

So the Vercel frontend `https://frontend-rho-eight-72.vercel.app` is allowed. No change needed for CORS if you only use that frontend.

---

## 3. Backend env (Render)

On Render, the backend service should have at least:

- **DATABASE_URL** – PostgreSQL connection string
- **SECRET_KEY** – JWT signing secret
- **BACKEND_CORS_ORIGINS** – `https://frontend-rho-eight-72.vercel.app` (or set in `render.yaml`)
- **FRONTEND_URL** – `https://frontend-rho-eight-72.vercel.app` (for emails/links)

---

## 4. How to verify the connection

1. **Backend reachable**
   - Open: `https://<your-backend-url>.onrender.com/health`  
   - Expect: `{"status":"healthy"}` (or 200). If it hangs or 404, the backend URL is wrong or the service is down.

2. **CORS**
   - Open: `https://<your-backend-url>.onrender.com/debug/cors`  
   - Check that `cors_origins` or the regex includes your frontend origin (e.g. `https://frontend-rho-eight-72.vercel.app` or `*.vercel.app`).

3. **Frontend env**
   - In the browser on your Vercel app, open DevTools → Network, trigger login or any API call.
   - Check the **Request URL**: it must be `https://<your-backend-url>.onrender.com/...`.  
   - If it’s something else (e.g. old Render URL or localhost), set `NEXT_PUBLIC_API_URL` in Vercel and redeploy.

4. **Login**
   - Sign in on the frontend. If it stays loading, check Network: request to `/api/v1/auth/login` should go to your backend; if it fails, see LOGIN_TROUBLESHOOTING.md.

---

## 5. Quick checklist

| Check | Action |
|-------|--------|
| Backend URL | Render dashboard → copy service URL. In Vercel set `NEXT_PUBLIC_API_URL` to that URL (no trailing slash). |
| Frontend URL on backend | Render env: `BACKEND_CORS_ORIGINS` and `FRONTEND_URL` = `https://frontend-rho-eight-72.vercel.app` (or your Vercel URL). |
| Backend env | Render: `DATABASE_URL`, `SECRET_KEY` set. |
| After changing env | Redeploy frontend (Vercel) and/or backend (Render) so new values are used. |
