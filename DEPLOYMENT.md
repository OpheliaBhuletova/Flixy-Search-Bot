# Deployment Guide - Option 2: Kurigram with Docker

This bot has been configured to use **Kurigram** framework with Docker-based deployment.

## Setup Overview

### Files Added/Modified:
- **Dockerfile** - Updated with git installation and configuration for Kurigram git clone
- **requirements.txt** - Uses git+https URL for Kurigram repository
- **.buildpacks** - Heroku buildpack configuration
- **runtime.txt** - Python 3.11.13 specification
- **koyeb.json** - Koyeb deployment configuration
- **.dockerignore** - Docker build optimization

---

## Deployment Platforms

### 🔵 Koyeb Deployment

1. **Connect your Git repository** to Koyeb
2. **Configure Build Settings**:
   - Buildpack: Docker
   - Dockerfile: `./Dockerfile`
   - Run command: `python -m bot.main`

3. **Set Environment Variables** in Koyeb dashboard:
   - `API_ID` - Your Telegram API ID
   - `API_HASH` - Your Telegram API Hash
   - `BOT_TOKEN` - Your bot token
   - `DATABASE_URL` - MongoDB connection URL
   - All other bot configuration variables

4. **Deploy**: Push to main branch and Koyeb will auto-deploy

---

### 🟣 Heroku Deployment

1. **Install Heroku CLI**: `npm install -g heroku`

2. **Login**: `heroku login`

3. **Create App**:
   ```bash
   heroku create your-app-name
   ```

4. **Set Environment Variables**:
   ```bash
   heroku config:set API_ID=your_api_id
   heroku config:set API_HASH=your_api_hash
   heroku config:set BOT_TOKEN=your_bot_token
   heroku config:set DATABASE_URL=your_mongodb_url
   ```

5. **Deploy**:
   ```bash
   git push heroku main
   ```

---

### 🐳 Docker Local Testing

```bash
# Build image
docker build -t flixy-bot .

# Run with environment variables
docker run --env-file .env flixy-bot
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'kurigram'"
**Cause**: Docker build failed to clone Kurigram repository
**Solution**: 
- Ensure internet connectivity
- Check GitHub API rate limits
- Verify `requirements.txt` has correct git URL

### "Failed to authenticate"
**Cause**: GitHub authentication issues
**Solution**: The Dockerfile is configured to use HTTPS URLs without auth (public repos). If you need private repos, configure SSH keys in build settings.

### "Build timeout"
**Cause**: Kurigram clone taking too long
**Solution**: The dependency should cache after first successful build

---

## Kurigram Information

- **Repository**: https://github.com/kurigram/kurigram
- **Branch**: main
- **Alternative**: Can fallback to Pyrogram v2.0+ if issues persist
- **Why Kurigram**: Enhanced maintenance, better performance, 100% API-compatible

---

## Local Development Setup

1. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create `.env` file with your credentials:
   ```env
   API_ID=123456789
   API_HASH=abcdef123456
   BOT_TOKEN=your_token_here
   DATABASE_URL=mongodb://...
   ```

4. Run bot:
   ```bash
   python -m bot.main
   ```

---

## Notes

- Ensure all environment variables are set before deployment
- MongoDB connection must be accessible from deployment platform
- Rate limiting is handled automatically by Kurigram
- Logs are stored in `logs/` directory

