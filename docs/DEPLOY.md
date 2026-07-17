# 🚀 Deploy to Streamlit Cloud

Deploy your GC-MS AI Analyzer so anyone can access it via a public URL — no installation, no data download.

## One-Time Setup (3 minutes)

### Step 1: Sign in to Streamlit Cloud

Go to **[share.streamlit.io](https://share.streamlit.io)** → **Sign in with GitHub**

### Step 2: Deploy

1. Click **"New app"**
2. Select:
   - **Repository**: `Tina-atk-love/gcms-ai-analyzer`
   - **Branch**: `master`
   - **Main file path**: `app.py`
3. Click **"Deploy!"**

### Step 3: Wait ~2 minutes

Streamlit Cloud will:
- Install Python dependencies from `requirements.txt`
- Start the app
- Give you a URL like `https://your-app.streamlit.app`

### Step 4: Share the URL

Anyone with the link can:
- ☕ Click **"Try Demo"** — instant coffee roasting analysis (no data needed)
- 🔑 Enter their own DeepSeek API key for AI features
- 📤 Upload their own `.D` ZIP or CSV files
- 📊 Explore all 50+ analysis tools

---

## What Works on Cloud

| Feature | Cloud | Notes |
|---------|-------|-------|
| ☕ Demo Mode | ✅ | Pre-loaded, no setup |
| 📊 Charts & Plots | ✅ | Plotly interactive + matplotlib |
| 👃 OAV / ROVA | ✅ | Built-in odor threshold DB |
| 📈 Statistics | ✅ | ANOVA, PCA, PLS-DA, RF |
| 🔍 MassBank Search | ✅ | 139K MS2 spectra |
| 🌐 MoNA API | ✅ | 1M+ spectra, live search |
| 🤖 AI Agent | ✅ | Requires user's DeepSeek API key |
| 📤 Upload .D ZIP | ✅ | Drag & drop, auto-extract |
| 📥 Export Reports | ✅ | Excel, Word, HTML |

## What Doesn't (local only)

| Feature | Why |
|---------|-----|
| 🔬 NIST Local Library | Requires local .L files (use MassBank + MoNA instead) |
| 💻 CLI Mode | Cloud is web-only (use `gcms_agent.py` locally for CLI) |

---

## Custom Domain (Optional)

1. Go to your app settings on Streamlit Cloud
2. Add your custom domain
3. Update DNS CNAME record

---

## Update the App

Just push to GitHub — Streamlit Cloud auto-redeploys:

```bash
git push origin master
# App updates within ~30 seconds
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Out of memory" | Reduce `maxUploadSize` in `.streamlit/config.toml` |
| App won't start | Check Streamlit Cloud logs in app settings |
| Slow first load | Normal — dependencies install on first deploy |
| "Module not found" | Make sure the import is in `requirements.txt` |
