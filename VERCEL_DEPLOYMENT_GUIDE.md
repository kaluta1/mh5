# Vercel Deployment Guide for MyHigh5

This guide explains how to deploy the entire MyHigh5 project (frontend + backend) on Vercel.

## 📋 Overview

- **Frontend**: Next.js 14 → Deploys directly on Vercel
- **Backend**: FastAPI → Adapted for Vercel Serverless Functions
- **Background Tasks**: Handled via Vercel Cron Jobs
- **Database**: PostgreSQL (Neon) → External service
- **Storage**: AWS S3 or Vercel Blob → External service

---

## ⚠️ Important Limitations

### What Works on Vercel:
✅ Frontend (Next.js)  
✅ API endpoints (FastAPI as serverless functions)  
✅ Database connections (PostgreSQL)  
✅ Static file serving  
✅ Cron jobs for scheduled tasks  

### What Doesn't Work:
❌ Long-running background processes (schedulers)  
❌ WebSocket connections (Socket.IO)  
❌ Persistent connections  
❌ File uploads to local storage (use S3/Vercel Blob)  

### Solutions:
- **Background Tasks**: Use Vercel Cron Jobs (configured in `vercel.json`)
- **WebSockets**: Use external service (Pusher, Ably) or disable
- **File Storage**: Use AWS S3 or Vercel Blob Storage

---

## 🚀 Deployment Steps

### Step 1: Prepare Repository

1. **Ensure all files are committed:**
```bash
git add .
git commit -m "Prepare for Vercel deployment"
```

2. **Verify file structure:**
```
mh5-1/
├── frontend/          # Next.js app
├── backend/           # FastAPI app
│   └── api/           # Serverless adapter
│       ├── index.py   # Main handler
│       └── requirements.txt
├── vercel.json        # Vercel configuration
└── .env.example       # Environment variables template
```

### Step 2: Install Vercel CLI

```bash
npm install -g vercel
```

### Step 3: Login to Vercel

```bash
vercel login
```

### Step 4: Configure Environment Variables

Create a `.env` file or set in Vercel dashboard:

#### Frontend Environment Variables:
```env
NEXT_PUBLIC_API_URL=https://your-project.vercel.app/api
NEXT_PUBLIC_REOWN_PROJECT_ID=your_reown_project_id
```

#### Backend Environment Variables:
```env
# Database
DATABASE_URL=postgresql://user:password@host:port/db?sslmode=require

# Security
SECRET_KEY=your_secret_key_here
ALGORITHM=HS256

# CORS
BACKEND_CORS_ORIGINS=https://your-project.vercel.app,https://www.myhigh5.com

# Email (Resend)
RESEND_API_KEY=your_resend_api_key
EMAIL_FROM=MyHigh5 <infos@myhigh5.com>

# Storage (AWS S3)
STORAGE_TYPE=s3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_S3_BUCKET=your_bucket_name
AWS_REGION=us-east-1

# Redis (optional, for caching)
REDIS_URL=redis://your_redis_url

# BSC Payment
BSC_PAYMENT_CONTRACT=0x...
BSC_USDT_ADDRESS=0x...
BSC_CHAIN_ID=56
BSC_RPC_URL=https://bsc-dataseed.binance.org

# KYC (Shufti Pro)
SHUFTI_CLIENT_ID=your_client_id
SHUFTI_SECRET_KEY=your_secret_key
SHUFTI_CALLBACK_URL=https://your-project.vercel.app/api/v1/kyc/callback
SHUFTI_REDIRECT_URL=https://your-project.vercel.app/kyc/complete
```

### Step 5: Deploy to Vercel

#### Option A: Via Vercel Dashboard (Recommended)

1. Go to [vercel.com](https://vercel.com)
2. Click "New Project"
3. Import your Git repository
4. Configure:
   - **Framework Preset**: Next.js
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `.next`
5. Add all environment variables
6. Click "Deploy"

#### Option B: Via CLI

```bash
# From project root
vercel

# Follow prompts:
# - Set up and deploy? Yes
# - Which scope? (select your account)
# - Link to existing project? No
# - Project name? myhigh5
# - Directory? ./
# - Override settings? No
```

### Step 6: Configure Vercel Settings

After initial deployment, configure:

1. **Go to Project Settings → General**
   - Root Directory: Leave empty (handled by vercel.json)
   
2. **Go to Project Settings → Environment Variables**
   - Add all backend environment variables
   - Add all frontend environment variables (with `NEXT_PUBLIC_` prefix)

3. **Go to Project Settings → Functions**
   - Function Region: Choose closest to your database
   - Max Duration: 60s (for serverless functions)

---

## 📁 File Structure Explained

### `vercel.json`
Routes API requests to backend serverless functions and frontend to Next.js.

### `backend/api/index.py`
Serverless adapter that wraps FastAPI app with Mangum for Vercel compatibility.

### `backend/api/requirements.txt`
Minimal Python dependencies for serverless functions (smaller bundle size).

---

## 🔧 Post-Deployment Configuration

### 1. Update Frontend API URL

Update `frontend/lib/config.ts`:

```typescript
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://your-project.vercel.app/api';
```

### 2. Update CORS Origins

Ensure `BACKEND_CORS_ORIGINS` includes your Vercel domain:
```env
BACKEND_CORS_ORIGINS=https://your-project.vercel.app,https://www.myhigh5.com
```

### 3. Configure Cron Jobs (Optional)

Add to `vercel.json`:

```json
{
  "crons": [
    {
      "path": "/api/cron/payments",
      "schedule": "*/2 * * * *"
    },
    {
      "path": "/api/cron/contest-status",
      "schedule": "*/5 * * * *"
    }
  ]
}
```

### 4. Database Migrations

Run migrations manually or via Vercel CLI:

```bash
# Connect to Vercel environment
vercel env pull .env.local

# Run migrations
cd backend
alembic upgrade head
```

---

## 🐛 Troubleshooting

### Issue: API Routes Not Working

**Solution:**
- Check `vercel.json` routes configuration
- Verify `backend/api/index.py` exists
- Check function logs in Vercel dashboard

### Issue: Database Connection Errors

**Solution:**
- Verify `DATABASE_URL` is set correctly
- Check SSL mode: `?sslmode=require`
- Ensure database allows connections from Vercel IPs

### Issue: Background Tasks Not Running

**Solution:**
- Background schedulers don't work on serverless
- Use Vercel Cron Jobs instead (see Step 3 above)
- Or use external cron service (cron-job.org, EasyCron)

### Issue: File Uploads Failing

**Solution:**
- Local storage doesn't work on serverless
- Configure `STORAGE_TYPE=s3` in environment variables
- Set up AWS S3 bucket and credentials

### Issue: WebSocket Not Working

**Solution:**
- Socket.IO doesn't work on serverless functions
- Use external WebSocket service (Pusher, Ably)
- Or disable real-time features

---

## 📊 Monitoring

### Vercel Dashboard
- View function logs
- Monitor API usage
- Check deployment status
- View analytics

### Function Logs
```bash
vercel logs
```

### Real-time Logs
```bash
vercel logs --follow
```

---

## 🔄 Continuous Deployment

Vercel automatically deploys on:
- Push to main branch
- Pull request creation
- Manual trigger

### Branch Deployments
- `main` → Production
- Other branches → Preview deployments

---

## 💰 Cost Considerations

### Vercel Free Tier:
- ✅ 100GB bandwidth/month
- ✅ 100 serverless function executions/day
- ✅ Unlimited static deployments
- ✅ Automatic SSL

### Vercel Pro ($20/month):
- ✅ Unlimited bandwidth
- ✅ Unlimited function executions
- ✅ Team collaboration
- ✅ Advanced analytics

---

## 🚨 Important Notes

1. **Background Tasks**: Must use Vercel Cron or external service
2. **Database**: Use connection pooling (Neon has built-in pooling)
3. **File Storage**: Must use S3 or Vercel Blob (not local storage)
4. **WebSockets**: Not supported, use external service
5. **Cold Starts**: First request may be slow (~1-2s)

---

## ✅ Deployment Checklist

- [ ] Repository pushed to GitHub/GitLab
- [ ] Environment variables configured
- [ ] Database migrations run
- [ ] S3 bucket configured (if using file uploads)
- [ ] CORS origins updated
- [ ] Frontend API URL updated
- [ ] Cron jobs configured (if needed)
- [ ] Test deployment on preview branch
- [ ] Monitor logs for errors
- [ ] Update DNS (if using custom domain)

---

## 📚 Additional Resources

- [Vercel Documentation](https://vercel.com/docs)
- [FastAPI on Vercel](https://vercel.com/guides/deploying-fastapi-with-vercel)
- [Next.js Deployment](https://nextjs.org/docs/deployment)
- [Vercel Serverless Functions](https://vercel.com/docs/functions)

---

## 🆘 Support

If you encounter issues:
1. Check Vercel function logs
2. Verify environment variables
3. Test database connection
4. Review this guide's troubleshooting section
