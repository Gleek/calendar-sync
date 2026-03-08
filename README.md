# calsync

Sync Google Calendar events to a local SQLite database and export them as an org-mode file.

Designed for people who want to own their calendar data in queryable (SQL) and readable (org-mode) formats — without lock-in to any calendar UI.

## What it does

- **Incremental sync** from Google Calendar API to a local SQLite database using sync tokens
- **Expands recurring events** into individual instances (no RRULE parsing needed for queries)
- **Exports to org-mode** with a year/month/week/day hierarchy
- **Calendar whitelist** to sync only the calendars you care about
- **Display name mapping** so email-based calendar IDs show as readable names

## Install

```
git clone https://github.com/yourusername/calsync.git
cd calsync
uv venv && uv pip install -e .
```

Or with pip:

```
pip install -e .
```

Requires Python 3.11+.

## Setup

### 1. Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the **Google Calendar API**
4. Go to **APIs & Services > Credentials**
5. Create an **OAuth 2.0 Client ID** (Desktop application)
6. Download the JSON and save it as `~/.config/calsync/credentials.json`

If you're the only user, you don't need to verify your app — just add your Google account as a test user under **OAuth consent screen > Test users**.

### 2. Configuration

Create `~/.config/calsync/config.toml`:

```toml
# How far back to sync on first run
sync_start = "2019-01-01"

# Only sync these calendars (by name as shown in Google).
# Remove this to sync all calendars.
calendars = [
    "primary@gmail.com",
    "Work",
    "Family Events",
]

# Generate org-babel analysis blocks in export (default: true)
babel_analysis = true

# Optional: rename calendars in the org export
[display_names]
"primary@gmail.com" = "Default"
```

## Usage

### Sync

```
# First run: opens browser for OAuth, then does a full sync
calsync sync

# Subsequent runs: incremental sync (only changed events)
calsync sync

# Force a full re-sync
calsync sync --full
```

### Export

```
# Generate calendar.org from the database
calsync export

# Custom output path
calsync export -o ~/org/calendar.org
```

### Options

```
calsync --db-path /path/to/calendar.db sync    # custom database location
calsync --config /path/to/config.toml sync      # custom config file
calsync sync --config-dir /path/to/auth/dir     # custom auth directory
```

## Org-mode output

The export produces a file like this:

```org
* 2024
** Analysis
#+begin_src sqlite :db ~/calendar.db :results table :colnames yes
SELECT c.summary as calendar,
       ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours
FROM events e
JOIN calendars c ON e.calendar_id = c.id
WHERE e.start_time >= '2024-01-01' AND e.start_time < '2025-01-01'
  AND e.all_day = 0
GROUP BY c.summary
ORDER BY hours DESC;
#+end_src
** Nov
*** Analysis
#+begin_src sqlite :db ~/calendar.db :results table :colnames yes
...
#+end_src
*** Week 46
**** Analysis
#+begin_src sqlite :db ~/calendar.db :results table :colnames yes
...
#+end_src
**** [2024-11-14 Thu]
***** 09:00-09:30 [Work] Team Standup
***** 10:00-12:00 [Default] Deep Focus
***** 14:00-15:30 [Work] Client Call
***** 18:00-20:00 [Family Events] Dinner
**** [2024-11-15 Fri]
***** [Family Events] Birthday Party
```

Each year, month, and week heading includes an org-babel analysis block that sums hours per calendar for that period. Execute with `C-c C-c` in Emacs. Disable with `babel_analysis = false` in config.

All-day events omit the time range. Calendar names appear in square brackets.

## SQLite schema

The database has three tables:

**calendars**
| Column | Type | Description |
|---|---|---|
| id | TEXT | Google calendar ID (primary key) |
| summary | TEXT | Calendar name |
| description | TEXT | Calendar description |
| time_zone | TEXT | Calendar timezone |
| color | TEXT | Calendar color |

**events**
| Column | Type | Description |
|---|---|---|
| id | TEXT | Event ID (composite PK with calendar_id) |
| calendar_id | TEXT | Foreign key to calendars |
| summary | TEXT | Event title |
| description | TEXT | Event description |
| location | TEXT | Event location |
| start_time | TEXT | ISO 8601 start time |
| end_time | TEXT | ISO 8601 end time |
| duration_minutes | INTEGER | Computed duration |
| all_day | INTEGER | 1 if all-day event |
| recurring_event_id | TEXT | Parent recurring event ID |
| status | TEXT | Event status |
| created | TEXT | Creation timestamp |
| updated | TEXT | Last update timestamp |

**sync_state**
| Column | Type | Description |
|---|---|---|
| calendar_id | TEXT | Foreign key to calendars |
| sync_token | TEXT | Google sync token |
| last_synced_at | TEXT | Last sync timestamp |

## Querying with SQL

Since the data lives in SQLite, you can query it directly:

```sql
-- Hours per calendar this week
SELECT c.summary, ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours
FROM events e
JOIN calendars c ON e.calendar_id = c.id
WHERE e.start_time >= date('now', '-7 days')
GROUP BY c.summary
ORDER BY hours DESC;

-- Daily breakdown for a specific month
SELECT date(e.start_time) as day, c.summary, ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours
FROM events e
JOIN calendars c ON e.calendar_id = c.id
WHERE e.start_time LIKE '2024-11%'
GROUP BY day, c.summary
ORDER BY day, hours DESC;

-- Busiest days
SELECT date(e.start_time) as day, COUNT(*) as events, ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours
FROM events e
WHERE e.all_day = 0
GROUP BY day
ORDER BY hours DESC
LIMIT 10;
```

### With Emacs org-babel

Add SQL blocks directly in your org files:

```org
#+begin_src sqlite :db ~/calendar.db :results table :colnames yes
SELECT c.summary as calendar, ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours
FROM events e
JOIN calendars c ON e.calendar_id = c.id
WHERE e.start_time >= date('now', '-7 days')
GROUP BY c.summary
ORDER BY hours DESC;
#+end_src
```

Execute with `C-c C-c` to get results inline.

## File locations

| File | Location |
|---|---|
| OAuth credentials | `~/.config/calsync/credentials.json` |
| OAuth token | `~/.config/calsync/token.json` |
| Config | `~/.config/calsync/config.toml` |
| Database | `./calendar.db` (configurable) |
| Org export | `./calendar.org` (configurable) |

## License

MIT
