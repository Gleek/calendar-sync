from datetime import date, datetime

from . import db

MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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
    events = db.get_all_events(conn)

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

        if month != current_month:
            current_month = month
            current_week = None
            current_day = None
            lines.append(f"** {MONTH_ABBR[month]}")

        if iso_week != current_week:
            current_week = iso_week
            current_day = None
            lines.append(f"*** Week {iso_week:02d}")

        if day != current_day:
            current_day = day
            day_name = DAY_ABBR[day.weekday()]
            lines.append(f"**** [{day.isoformat()} {day_name}]")

        lines.append(format_event_line(event, display_names))

    content = "\n".join(lines) + "\n" if lines else ""

    with open(output_path, "w") as f:
        f.write(content)

    return len(events)
