# Fix 404 NOT_FOUND on Vercel (Contest / Nominate / Apply)

If you see a raw Vercel error like:

```
404: NOT_FOUND
Code: NOT_FOUND
ID: cdg1::xxxx-...
```

the request is **not** reaching your Next.js app. Fix it as follows.

## Required: Set Root Directory to `frontend`

1. Open **Vercel Dashboard** → your project (frontend).
2. Go to **Settings** → **General**.
3. Under **Root Directory**, click **Edit**.
4. Enter: **`frontend`**
5. Save and **redeploy** the project.

With this, Vercel builds and serves only the `frontend` app. Routes like `/dashboard/contests/4/apply` are then handled by Next.js and the custom 404 page is used instead of the generic Vercel 404.

## If you cannot use Root Directory

If you must deploy from the repo root (no Root Directory):

- Keep the root `vercel.json` with `"dest": "/$1"` (do **not** use `"dest": "frontend/$1"`).
- Ensure **Build Command** runs from `frontend` (e.g. `cd frontend && npm run build`) and **Output Directory** is `frontend/.next`.

Prefer setting **Root Directory** to **`frontend`** to avoid 404s and build issues.

---

# Fix CORS errors (frontend ↔ backend on Render)

If the browser shows:

```
Access to XMLHttpRequest at 'https://mh5-backend.onrender.com/...' from origin 'https://frontend-rho-eight-72.vercel.app'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

1. **Redeploy the backend** (Render) so the latest CORS middleware is live.
2. **Optional on Render:** In the backend service → **Environment** → add:
   - **Key:** `BACKEND_CORS_ORIGINS`
   - **Value:** `https://frontend-rho-eight-72.vercel.app,https://myhigh5.vercel.app`
   Then redeploy the backend.
3. **Cold start:** On Render free tier the first request after idle can timeout; the backend then sends no response, so the browser reports CORS. Retry the request once the service has woken up, or use a keep-warm ping.
