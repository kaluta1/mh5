# Fix Vercel Deployment Permission Error

## Error
```
Error: Git author godsonferdinand7@gmail.com must have access to the team dsm's projects on Vercel to create deployments.
```

## Solutions

### Option 1: Add Email to Vercel Team (Recommended)
1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Navigate to your team "dsm" → **Settings** → **Members**
3. Add `godsonferdinand7@gmail.com` as a team member
4. Retry deployment: `vercel --prod`

### Option 2: Change Git Commit Author
If you want to use a different email for this deployment:

```powershell
# Set git config for this repo
git config user.email "kalutashoppingmall@gmail.com"
git config user.name "Morice"

# Amend the last commit with new author
git commit --amend --author="Morice <kalutashoppingmall@gmail.com>" --no-edit

# Force push (if needed)
git push --force
```

### Option 3: Deploy via GitHub (Easiest)
Instead of using `vercel --prod` CLI:
1. Push your changes to GitHub
2. Vercel will automatically deploy from GitHub
3. This uses the GitHub integration, not CLI author

### Option 4: Use Vercel Dashboard
1. Go to Vercel Dashboard → Your Project
2. Click **Deployments** → **Create Deployment**
3. Select your branch and deploy manually

## Quick Fix (Temporary)
If you need to deploy immediately and can't change team settings:

```powershell
# Use --force flag (may still fail if team settings block it)
vercel --prod --force
```

**Note:** The best solution is Option 1 - adding the email to your Vercel team.
