from datetime import date, datetime
from pathlib import Path

from . import db

MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _babel_block(db_path, query, heading_level):
    """Generate an org-babel SQL block."""
    prefix = "*" * (heading_level + 1)
    return (
        f"{prefix} Analysis\n"
        f"#+begin_src sqlite :db {db_path} :results table :colnames yes\n"
        f"{query}\n"
        f"#+end_src"
    )


def _year_analysis(db_path, year):
    query = (
        f"SELECT c.summary as calendar,\n"
        f"       ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours\n"
        f"FROM events e\n"
        f"JOIN calendars c ON e.calendar_id = c.id\n"
        f"WHERE e.start_time >= '{year}-01-01' AND e.start_time < '{year + 1}-01-01'\n"
        f"  AND e.all_day = 0\n"
        f"GROUP BY c.summary\n"
        f"ORDER BY hours DESC;"
    )
    return _babel_block(db_path, query, 1)


def _month_analysis(db_path, year, month):
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year = year + 1
    query = (
        f"SELECT c.summary as calendar,\n"
        f"       ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours\n"
        f"FROM events e\n"
        f"JOIN calendars c ON e.calendar_id = c.id\n"
        f"WHERE e.start_time >= '{year}-{month:02d}-01'\n"
        f"  AND e.start_time < '{next_year}-{next_month:02d}-01'\n"
        f"  AND e.all_day = 0\n"
        f"GROUP BY c.summary\n"
        f"ORDER BY hours DESC;"
    )
    return _babel_block(db_path, query, 2)


def _week_analysis(db_path, year, week):
    query = (
        f"SELECT c.summary as calendar,\n"
        f"       ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours\n"
        f"FROM events e\n"
        f"JOIN calendars c ON e.calendar_id = c.id\n"
        f"WHERE strftime('%Y', e.start_time) = '{year}'\n"
        f"  AND CAST(strftime('%W', e.start_time) AS INTEGER) = {week}\n"
        f"  AND e.all_day = 0\n"
        f"GROUP BY c.summary\n"
        f"ORDER BY hours DESC;"
    )
    return _babel_block(db_path, query, 3)


def format_event_line(event, display_names):
    """Format a single event as an org-mode line."""
    calendar_name = display_names.get(event["calendar_name"], event["calendar_name"])

    if event["all_day"]:
        return f"***** [{calendar_name}] {event['summary'] or '(no title)'}"

    start = datetime.fromisoformat(event["start_time"])
    end_str = ""
    if event["end_time"]:
        end = datetime.fromisoformat(event["end_time"])
        end_str = f"-{end.strftime('%H:%M')}"

    time_range = f"{start.strftime('%H:%M')}{end_str}"
    return f"***** {time_range} [{calendar_name}] {event['summary'] or '(no title)'}"


def export_org(conn, output_path="calendar.org", config=None):
    """Generate calendar.org from database."""
    display_names = (config or {}).get("display_names", {})
    babel = (config or {}).get("babel_analysis", True)
    events = db.get_all_events(conn)

    db_path = None
    if babel:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        db_path = str(Path(db_path).resolve())

    current_year = None
    current_month = None
    current_week = None
    current_day = None

    lines = []

    for event in events:
        start_str = event["start_time"]
        if event["all_day"]:
            dt = date.fromisoformat(start_str)
        else:
            dt = datetime.fromisoformat(start_str).date()

        year = dt.year
        month = dt.month
        iso_week = dt.isocalendar()[1]
        day = dt

        if year != current_year:
            current_year = year
            current_month = None
            current_week = None
            current_day = None
            lines.append(f"* {year}")
            if babel:
                lines.append(_year_analysis(db_path, year))

        if month != current_month:
            current_month = month
            current_week = None
            current_day = None
            lines.append(f"** {MONTH_ABBR[month]}")
            if babel:
                lines.append(_month_analysis(db_path, year, month))

        if iso_week != current_week:
            current_week = iso_week
            current_day = None
            lines.append(f"*** Week {iso_week:02d}")
            if babel:
                lines.append(_week_analysis(db_path, year, iso_week))

        if day != current_day:
            current_day = day
            day_name = DAY_ABBR[day.weekday()]
            lines.append(f"**** [{day.isoformat()} {day_name}]")

        lines.append(format_event_line(event, display_names))

    content = "\n".join(lines) + "\n" if lines else ""

    with open(output_path, "w") as f:
        f.write(content)

    return len(events)
