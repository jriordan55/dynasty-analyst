# Publish to GitHub

## Streamlit Cloud — keep the live app updated

The app on Streamlit Cloud pulls from `main` on GitHub and **redeploys automatically** after each push.

After any code change:

```powershell
git add .
git commit -m "describe the change"
git push origin main
```

Wait ~1–2 minutes, then refresh the app on your phone. Do not commit `config/league.json` or `.env`.

---

Follow these steps once to get a link you can use and share.

## 1. Create the repo on GitHub

1. Go to [github.com/new](https://github.com/new)
2. Name it `dynasty-analyst` (or anything you like)
3. Leave it **Public**
4. Do **not** add README or .gitignore (we already have them)
5. Click **Create repository**

## 2. Push from your machine

In PowerShell, from this folder:

```powershell
cd "c:\Users\student\Documents\fantasy football"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/dynasty-analyst.git
git push -u origin main
```

Replace `YOUR_GITHUB_USERNAME` with your GitHub handle.

## 3. Get a live web app URL (free)

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click **New app**
4. Select your `dynasty-analyst` repo
5. Main file path: `app.py`
6. Click **Deploy**

You'll get a URL like: `https://dynasty-analyst-abc123.streamlit.app`

Open it on your phone or laptop — enter league ID `1363674260144418816` and username `jon696969`.

## 4. Run locally anytime

```powershell
cd "c:\Users\student\Documents\fantasy football"
.venv\Scripts\activate
streamlit run app.py
```

Opens at http://localhost:8501

## Your league (already configured locally)

- **League:** Tupper's dog house
- **League ID:** `1363674260144418816`
- **Username:** `jon696969`

These are saved in `config/league.json` on your machine only (not pushed to GitHub).
