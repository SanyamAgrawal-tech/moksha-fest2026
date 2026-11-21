# Moksha 2026 - NSUT Cultural Fest Portal

A full-stack web application designed for **Moksha (NSUT Cultural Fest)** that manages student/visitor registrations, ticketing passes, vendor stall bookings, and sponsorships. Built with **Flask (Python)**, **SQLite / Turso (3NF relational schema)**, and a modern responsive frontend.

---

## 🌐 Live Web & Admin Deployment on Vercel

Both the **Main Website** and **Admin Portal** are unified in a single deployment:

- **Public Site**: `https://<your-project>.vercel.app/`
  - Students & Visitors: multi-step registration, pass selection, event selection with seat tracking.
  - Vendors & Stalls: stall bookings with power/equipment requirements.
  - Sponsors: sponsorship tier applications.
  - Feedback & Inquiries.
- **Admin Portal**: `https://<your-project>.vercel.app/admin` (or `/admin/login`)
  - **Password**: `moksha2026` (configurable via `ADMIN_PASSWORD` env var).
  - Real-time tabular dashboard for Participants, Registrations, Passes, Events, Vendors, and Feedback.
  - One-click **Export CSV** download for all registered attendees.
  - Auto-refreshes every 30 seconds.

---

## 🚀 How to Deploy to Vercel (1-Click)

### Option A: Using the automated helper
Inside the project folder, double-click:
```text
deploy.bat
```
This script will verify your Vercel login (opens your browser to authenticate if needed) and deploy straight to production with `npx vercel --prod --yes`.

### Option B: Using terminal commands
Open PowerShell in the project directory:
```powershell
cd "C:\Users\Arya Dasgupta\.gemini\antigravity\scratch\moksha_fest"
npx vercel login
npx vercel --prod
```

---

## 💾 Ensuring Data Persistence on Vercel (Cloud Database)

> **Why is this important?**  
> Vercel Serverless Functions have a read-only filesystem with temporary `/tmp`. By default, any local database resets when the serverless function goes to sleep.

To make **all registrations permanently stored and synced across all Vercel instances**:

1. Create a free account at [turso.tech](https://turso.tech) (100% free, no credit card required).
2. Install Turso CLI or create a database from their web dashboard named `moksha-db`:
   ```bash
   turso db create moksha-db
   turso db show moksha-db --url
   turso db tokens create moksha-db
   ```
3. In your **Vercel Project Dashboard** &rarr; **Settings** &rarr; **Environment Variables**, add:
   - `TURSO_DATABASE_URL`: `https://moksha-db-<username>.turso.io`
   - `TURSO_AUTH_TOKEN`: `<your-token>`
4. Redeploy on Vercel.  
   The application will automatically detect Turso and switch to **Persistent Cloud Database** mode. The green badge in `/admin` will confirm: `● Turso Cloud DB (Persistent)`.

*(When running locally on your computer with `python app.py`, it automatically uses local `moksha.db` with zero configuration).*

---

## 🛠️ Project Structure

```
moksha_fest/
├── app.py              # Flask server, REST APIs, business logic & admin auth
├── turso_db.py         # Lightweight cloud SQLite adapter (zero C dependencies)
├── schema.sql          # 3NF relational SQLite schema, triggers, and seed data
├── vercel.json         # Vercel serverless routing configuration
├── requirements.txt    # Flask>=3.0.0, requests>=2.31.0
├── deploy.bat          # Automated 1-click Vercel deployment helper
├── api/
│   └── index.py        # Vercel WSGI entrypoint
├── templates/
│   ├── index.html      # Public website (Students, Vendors, Sponsors, Confirmation)
│   ├── admin.html      # Live Admin Portal with CSV export & database status
│   └── admin_login.html# Secure Admin login
└── moksha.db           # Local SQLite database
```

---

## 💻 Running Locally

```powershell
cd "C:\Users\Arya Dasgupta\.gemini\antigravity\scratch\moksha_fest"
python app.py
```
Open **http://127.0.0.1:5000** in your browser.
