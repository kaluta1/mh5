# CORS Fix - Deployment Checklist

## ✅ Code Changes Made

1. ✅ Added `https://frontend-rho-eight-72.vercel.app` to CORS origins
2. ✅ Updated regex to allow all Vercel deployments: `^https://.*\.vercel\.app$`
3. ✅ Removed invalid wildcard from origins list

## 🚨 CRITICAL: Backend Must Be Redeployed

The CORS errors will continue until the backend is redeployed with the new configuration.

### Steps to Redeploy:

1. **Commit and Push Changes:**
   ```bash
   git add backend/main.py backend/app/core/config.py
   git commit -m "Fix CORS: Add Vercel frontend origin and regex pattern"
   git push origin main
   ```

2. **Render Auto-Deploy:**
   - Render should automatically detect the push and redeploy
   - Check Render dashboard → Your service → Logs to see deployment progress

3. **Manual Deploy (if needed):**
   - Go to Render Dashboard → Your Backend Service
   - Click **Manual Deploy** → **Deploy latest commit**

4. **Verify Deployment:**
   - Wait for deployment to complete (usually 2-5 minutes)
   - Check logs for: `CORS Origins configured: [...]`
   - Verify your Vercel URL is in the list

## 🔍 Verify CORS is Working

After redeploy, test in browser console on your Vercel frontend:

```javascript
fetch('https://mh5-backend.onrender.com/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'test', password: 'test' })
})
.then(r => console.log('CORS OK:', r.status))
.catch(e => console.error('CORS Error:', e))
```

If you see `CORS OK: 401` (or any status), CORS is working! (401 is expected for invalid credentials)

## ⚠️ If CORS Still Fails After Redeploy

1. **Check Render Logs:**
   - Look for the line: `CORS Origins configured: [...]`
   - Verify `https://frontend-rho-eight-72.vercel.app` is in the list

2. **Set Environment Variable (Alternative):**
   - Go to Render Dashboard → Environment
   - Add: `BACKEND_CORS_ORIGINS`
   - Value: `https://frontend-rho-eight-72.vercel.app,https://your-production.vercel.app`
   - Redeploy

3. **Check Backend URL:**
   - Verify backend URL is correct: `https://mh5-backend.onrender.com`
   - Test backend health: `curl https://mh5-backend.onrender.com/docs`

## 📝 Current Configuration

- **Frontend:** `https://frontend-rho-eight-72.vercel.app`
- **Backend:** `https://mh5-backend.onrender.com`
- **CORS Regex:** `^https://.*\.vercel\.app$` (allows all Vercel deployments)

## ✅ After Successful Deployment

- CORS errors should disappear
- Login should work
- All API endpoints accessible
- GraphQL queries should work
