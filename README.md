<<<<<<< HEAD
# Economical-Energy-Mix-Monitoring
Trying to demonstrate a correlation between the energy.mix of countries and their economics
=======
# ⚡ Energy & Economics Dashboard

An interactive, data-driven web application that explores the relationship between renewable energy investment and economic stability across European countries.

**Research thesis:** Countries that invested in renewable energy reduced their dependence on imported fossil fuels — leading to more stable electricity prices, lower energy inflation, and greater economic resilience.

---

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Local Setup](#local-setup)
- [Server Deployment](#server-deployment)
- [Data Sources](#data-sources)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Features

- **4 analysis tabs** — Structural view (5–10 years), Market dynamics (1–2 years), Operational view (days/weeks), Country comparison
- **3-tier energy classification** — Renewable (green) / Nuclear (purple) / Fossil (red)
- **Country comparison** with green/red win-loss highlighting and auto-generated causal narrative
- **CSV download** buttons for all datasets
- **Background scheduler** that pre-fetches data for top countries every 2 hours
- **SQLite cache** shared across all browser sessions, survives app restarts
- **URL state sharing** — bookmarkable views via query parameters
- **Sources & Data tab** and **How to Use tab** for academic and public audiences

---

## Project Structure

```
energy-app/
├── app.py                        # Main Streamlit application
├── requirements.txt              # Python dependencies
├── .env                          # Local API key (never commit)
├── .gitignore
│
├── data/
│   ├── __init__.py               # Required — can be empty
│   ├── fetcher.py                # ENTSO-E API retrieval
│   ├── eurostat.py               # Eurostat API retrieval
│   ├── processor.py              # Analytics and calculations
│   ├── cache_db.py               # SQLite cache engine
│   └── scheduler.py              # Background pre-fetch scheduler
│
└── .streamlit/
    └── secrets.toml              # API key for server deployment (never commit)
```

> **Important:** `data/__init__.py` must exist (can be completely empty).  
> Without it Python won't treat `data/` as a package and all imports will fail.

---

## Requirements

- Python 3.11 or higher
- A free ENTSO-E API key (see [Getting an API Key](#getting-an-api-key))
- Internet connection (Eurostat requires no key)

---

## Local Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd energy-app
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

> **Never use `--break-system-packages`** — always use a virtual environment on Debian/Ubuntu systems.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create the `data/__init__.py` file

```bash
touch data/__init__.py
```

### 5. Set your ENTSO-E API key

Create a `.env` file in the project root:

```bash
echo "ENTSOE_API_KEY=your-api-key-here" > .env
```

### 6. Run the app

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## Getting an API Key

1. Register for a free account at [transparency.entsoe.eu](https://transparency.entsoe.eu)
2. After logging in, go to **My Account Settings**
3. Generate a **Web API Security Token**
4. Copy the token — this is your `ENTSOE_API_KEY`

Eurostat data requires **no API key** and no registration.

---

## Server Deployment

### Streamlit Cloud

1. Push your code to GitHub (make sure `.env` and `.streamlit/secrets.toml` are in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your repository
3. In the app settings, add your secret:

```toml
# Streamlit Cloud → App Settings → Secrets
ENTSOE_API_KEY = "your-api-key-here"
```

4. Deploy — the app handles everything else automatically

### Self-hosted server (Linux)

**1. Clone and set up the environment:**

```bash
git clone <your-repo-url>
cd energy-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
touch data/__init__.py
```

**2. Create Streamlit secrets:**

```bash
mkdir -p .streamlit
cat > .streamlit/secrets.toml << EOF
ENTSOE_API_KEY = "your-api-key-here"
EOF
chmod 600 .streamlit/secrets.toml   # restrict read access
```

**3. Optional — set a custom cache directory:**

The SQLite cache defaults to `/tmp/energy_dashboard/cache.db`.  
To use a persistent location that survives server reboots:

```bash
echo "ENERGY_CACHE_DIR=/var/data/energy_cache" >> .streamlit/secrets.toml
```

Or set it as an environment variable:

```bash
export ENERGY_CACHE_DIR=/var/data/energy_cache
```

**4. Run with auto-restart using systemd:**

Create `/etc/systemd/system/energy-dashboard.service`:

```ini
[Unit]
Description=Energy & Economics Dashboard
After=network.target

[Service]
User=your-username
WorkingDirectory=/path/to/energy-app
ExecStart=/path/to/energy-app/.venv/bin/streamlit run app.py --server.port 8501 --server.headless true
Restart=always
RestartSec=5
Environment=ENERGY_CACHE_DIR=/var/data/energy_cache

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable energy-dashboard
sudo systemctl start energy-dashboard
sudo systemctl status energy-dashboard   # check it's running
```

**5. View logs:**

```bash
sudo journalctl -u energy-dashboard -f
```

---

## Data Sources

| Source | Dataset | Content | Update Frequency |
|--------|---------|---------|-----------------|
| [ENTSO-E](https://transparency.entsoe.eu) | Day-ahead prices | Hourly electricity prices (€/MWh) | Daily |
| [ENTSO-E](https://transparency.entsoe.eu) | Actual generation | Generation by source (MW) | Hourly |
| [ENTSO-E](https://transparency.entsoe.eu) | Installed capacity | Capacity per source (MW) | Annual |
| [Eurostat](https://ec.europa.eu/eurostat) | `prc_hicp_manr` | HICP inflation — general + energy (% YoY) | Monthly |
| [Eurostat](https://ec.europa.eu/eurostat) | `nrg_pc_204` | Household electricity prices (€/kWh) | Bi-annual |
| [Eurostat](https://ec.europa.eu/eurostat) | `nrg_ind_id` | Energy import dependency (%) | Annual |

---

## Configuration

### Cache TTLs

Default TTLs are defined in `data/cache_db.py`:

| Dataset | Default TTL | Rationale |
|---------|-------------|-----------|
| Day-ahead prices | 1 hour | Published daily |
| Generation mix | 1 hour | Near real-time |
| Installed capacity | 24 hours | Annual data |
| HICP inflation | 12 hours | Monthly release |
| Household prices | 72 hours | Bi-annual release |
| Import dependency | 72 hours | Annual release |

### Background scheduler

The scheduler pre-fetches data for these countries automatically:
`DE_LU, FR, ES, PL, AT, BE, NL, DK, CZ, IT_NORTH`

To add or remove countries, edit `TOP_COUNTRIES` in `data/scheduler.py`.

Schedule:
- **On startup** — Eurostat pre-fetch for all top countries (runs in background)
- **Every 2 hours** — ENTSO-E prices and generation refresh
- **02:00 daily** — Full Eurostat refresh for all top countries

### URL state sharing

After fetching data the URL updates automatically with query parameters:

```
http://localhost:8501/?country=DE_LU&compare=FR&years=5&start=2024-01-01&end=2025-01-01
```

Share this URL to give others a direct link to the same view.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'data'`**  
→ The `data/__init__.py` file is missing. Run: `touch data/__init__.py`

**`ENTSOE_API_KEY not found`**  
→ Check your `.env` file exists and contains `ENTSOE_API_KEY=your-key`.  
→ On a server, check `.streamlit/secrets.toml` contains `ENTSOE_API_KEY = "your-key"`.

**`cannot execute: required file not found` when running pip**  
→ Your virtual environment is broken. Delete and recreate it:
```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**503 errors from ENTSO-E**  
→ The ENTSO-E server is temporarily overloaded. The app retries automatically up to 3 times with exponential backoff. If it persists, wait a few minutes and try again.

**Household electricity prices return no data for a country**  
→ Not all countries report to Eurostat `nrg_pc_204` (Switzerland, Norway, and some non-EU states have limited coverage). The app shows an info message in this case.

**The virtual environment breaks after a system Python update**  
→ Delete and recreate the virtual environment (see above). This is expected behaviour on Debian/Ubuntu when Python is updated via `apt`.

**Cache is not persisting between restarts**  
→ Check the `ENERGY_CACHE_DIR` is set to a persistent directory (not `/tmp`, which is cleared on reboot on some systems). Set it in `.streamlit/secrets.toml` or as an environment variable.

---

## .gitignore

Make sure your `.gitignore` contains at minimum:

```
.venv/
venv/
.env
.streamlit/secrets.toml
.cache/
__pycache__/
*.pyc
*.db
```

---

## License

Data from ENTSO-E is free for non-commercial use with attribution.  
Eurostat data is freely reusable with source acknowledgement.

---

*Built with [Streamlit](https://streamlit.io) · [entsoe-py](https://github.com/EnergieID/entsoe-py) · [Plotly](https://plotly.com/python/) · [pandas](https://pandas.pydata.org)*
>>>>>>> 08d1b82 (project)
