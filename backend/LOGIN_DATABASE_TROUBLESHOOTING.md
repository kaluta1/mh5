# Login Database Connection Troubleshooting Guide

## Issue
Users are seeing "invalid" error messages when trying to log in, which may be caused by database connection issues.

## Changes Made

### 1. Enhanced Error Handling in Authentication (`app/crud/crud_user.py`)
- Added proper exception handling in `authenticate()`, `get_by_email()`, and `get_by_username()` methods
- Added detailed logging for database errors
- Errors are now properly propagated with context

### 2. Improved Login Endpoint (`app/api/api_v1/endpoints/auth.py`)
- Added try-catch around authentication call
- Better error logging for debugging
- Improved exception handling for login attempt logging

### 3. Enhanced Database Session Error Handling (`app/db/session.py`)
- Database connection errors now return HTTP 503 (Service Unavailable) instead of generic errors
- More detailed error logging
- Better error messages for users

## Diagnostic Steps

### Step 1: Test Database Connection
Run the diagnostic script to test the database connection:

```bash
cd backend
python test_db_connection.py
```

This will:
- Test basic database connectivity
- Check if the users table is accessible
- Verify query functionality

### Step 2: Test Authentication
Test authentication with specific credentials:

```bash
python test_db_connection.py <email_or_username> <password>
```

This will:
- Test user lookup by email
- Test user lookup by username
- Test full authentication flow
- Show detailed error messages if something fails

### Step 3: Check Environment Variables
Verify that `DATABASE_URL` is correctly set:

```bash
# Windows PowerShell
$env:DATABASE_URL

# Linux/Mac
echo $DATABASE_URL
```

The DATABASE_URL should be in the format:
```
postgresql://username:password@host:port/database?sslmode=require
```

For Neon PostgreSQL, it typically looks like:
```
postgresql://user:password@ep-xxx-xxx-pooler.region.aws.neon.tech/dbname?sslmode=require
```

### Step 4: Check Application Logs
Look for database connection errors in the application logs:

```bash
# If running with uvicorn
# Check console output for errors like:
# - "Database connection error"
# - "OperationalError"
# - "SQLAlchemyError"
```

### Step 5: Common Issues and Solutions

#### Issue: Connection Timeout
**Symptoms:**
- Errors mentioning "timeout" or "connection timed out"
- Slow response times

**Solutions:**
- Check internet connection
- Verify DATABASE_URL is correct
- Check if database server is accessible
- For Neon PostgreSQL, ensure SSL is enabled (`sslmode=require`)

#### Issue: SSL/TLS Errors
**Symptoms:**
- Errors mentioning "SSL" or "TLS"
- Connection refused errors

**Solutions:**
- Ensure `sslmode=require` is in DATABASE_URL for Neon PostgreSQL
- Check if SSL certificates are valid
- Verify database server supports SSL

#### Issue: Authentication Failed
**Symptoms:**
- "Email/Username or password incorrect" error
- User exists but login fails

**Solutions:**
- Verify user exists in database
- Check if password hash is correct
- Ensure user account is active (`is_active=True`)
- Check password verification logic

#### Issue: Database Not Found
**Symptoms:**
- "database does not exist" errors
- "relation does not exist" errors

**Solutions:**
- Verify database name in DATABASE_URL
- Check if migrations have been run
- Ensure users table exists

## Testing the Fix

1. **Start the backend server:**
   ```bash
   cd backend
   python start.py
   # or
   uvicorn main:app --reload
   ```

2. **Test login via API:**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/auth/login" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=test@example.com&password=testpassword"
   ```

3. **Check logs for detailed error messages:**
   - Database connection errors will now be logged with full details
   - Authentication failures will show which step failed

## Monitoring

After deploying these changes, monitor:
- Application logs for database connection errors
- Login success/failure rates
- Response times for login endpoint
- Database connection pool usage

## Additional Notes

- Database errors are now logged with full stack traces for debugging
- Users will see more helpful error messages (503 Service Unavailable) instead of generic "invalid" errors
- The diagnostic script can be run anytime to check database connectivity
- All database operations now have proper exception handling
