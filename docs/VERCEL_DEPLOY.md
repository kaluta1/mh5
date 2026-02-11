# Vercel deployment – avoid 404

If the frontend shows **404 NOT_FOUND** when you open the site:

## Fix: set Root Directory to `frontend`

1. Open **Vercel Dashboard** → your project → **Settings** → **General**.
2. Under **Root Directory**, click **Edit**.
3. Set it to **`frontend`** (no leading slash).
4. Save and **redeploy** the project.

Vercel will then build and serve the Next.js app from the `frontend` folder, and the root route (`/`) and all other routes should work.

## Why this happens

This repo has both `frontend` (Next.js) and `backend`. If Root Directory is left empty, Vercel uses the repo root and the build/routing can be wrong, which leads to 404. Setting Root Directory to **`frontend`** makes the frontend app the project root so deployment and routing work correctly.
