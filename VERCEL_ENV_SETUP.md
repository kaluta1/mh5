# Vercel Environment Variables Setup

## Critical: Set `NEXT_PUBLIC_API_URL` in Vercel

Your frontend is trying to connect to the backend but the environment variable is not set in Vercel.

### Steps to Fix:

1. **Go to Vercel Dashboard**
   - Visit: https://vercel.com/dashboard
   - Click on your project

2. **Navigate to Environment Variables**
   - Go to **Settings** → **Environment Variables**

3. **Add the Environment Variable**
   - **Key:** `NEXT_PUBLIC_API_URL`
   - **Value:** Your Render backend URL (e.g., `https://mh5-hbjp.onrender.com`)
   - **Environment:** Select **Production**, **Preview**, and **Development** (all three)

4. **Save and Redeploy**
   - Click **Save**
   - Go to **Deployments** tab
   - Click **⋯** (three dots) on the latest deployment
   - Click **Redeploy**

### Using Vercel CLI:

```bash
# Install Vercel CLI if needed
npm i -g vercel

# Login
vercel login

# Link project (if not already linked)
cd frontend
vercel link

# Add environment variable
vercel env add NEXT_PUBLIC_API_URL

# When prompted:
# - Value: https://your-backend.onrender.com
# - Environment: Production, Preview, Development (select all)
```

### Verify It's Set:

After redeploying, check the browser console. The API calls should go to your Render backend URL, not `localhost:8000`.

### Current Issues:

1. **404 Error:** GraphQL endpoint not found - likely because `NEXT_PUBLIC_API_URL` is not set
2. **Timeout:** Backend might be sleeping (Render free tier) or URL is incorrect
3. **Login Fails:** Cannot reach backend API

### After Setting Environment Variable:

1. ✅ Frontend will know where to send API requests
2. ✅ GraphQL queries will work
3. ✅ Login will connect to the correct backend
4. ✅ All API calls will use the Render backend URL

### Test After Setup:

1. Open your Vercel frontend URL
2. Open browser DevTools (F12) → **Console** tab
3. Check Network tab to see API requests
4. Verify requests go to `https://your-backend.onrender.com` not `localhost:8000`
