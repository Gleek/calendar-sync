from datetime import date, datetime
from pathlib import Path

from . import db

MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _top_level_analysis(db_path, start_date, end_date, calendar_names, display_names):
    """Generate top-level analysis section with table and trend chart."""
    table_query = (
        f"SELECT c.summary as calendar,\n"
        f"       ROUND(SUM(e.duration_minutes) / 60.0, 1) as hours\n"
        f"FROM events e\n"
        f"JOIN calendars c ON e.calendar_id = c.id\n"
        f"WHERE e.start_time >= '{start_date}'\n"
        f"  AND e.start_time < '{end_date}'\n"
        f"  AND e.all_day = 0\n"
        f"GROUP BY c.summary\n"
        f"ORDER BY hours DESC;"
    )

    # Build pivoted query with CASE per calendar
    case_columns = []
    for name in calendar_names:
        escaped = name.replace("'", "''")
        display = display_names.get(name, name)
        case_columns.append(
            f"       ROUND(SUM(CASE WHEN c.summary = '{escaped}' "
            f"THEN e.duration_minutes/60.0 ELSE 0 END), 1) as \"{display}\""
        )
    cases_str = ",\n".join(case_columns)

    trend_query = (
        f"SELECT date(e.start_time) as day,\n"
        f"{cases_str}\n"
        f"FROM events e\n"
        f"JOIN calendars c ON e.calendar_id = c.id\n"
        f"WHERE e.start_time >= '{start_date}'\n"
        f"  AND e.start_time < '{end_date}'\n"
        f"  AND e.all_day = 0\n"
        f"GROUP BY day\n"
        f"ORDER BY day;"
    )

    # Build gnuplot plot lines
    display_list = [display_names.get(n, n) for n in calendar_names]
    plot_lines = []
    for i, display in enumerate(display_list):
        col = i + 2  # column 1 is day, columns 2+ are calendars
        src = "data" if i == 0 else '""'
        plot_lines.append(f'{src} using 1:{col} with lines title "{display}"')
    plot_cmd = "plot " + ", \\\n     ".join(plot_lines)

    gnuplot_block = (
        f"set xdata time\n"
        f"set timefmt \"%Y-%m-%d\"\n"
        f"set format x \"%Y-%m\"\n"
        f"set xlabel \"Date\"\n"
        f"set ylabel \"Hours\"\n"
        f"set title \"Weekly hours by calendar\"\n"
        f"set key left top\n"
        f"set grid\n"
        f"set datafile separator \"\\t\"\n"
        f"{plot_cmd}"
    )

    return (
        f"* Analysis\n"
        f"** Hours by Calendar\n"
        f"#+begin_src sqlite :db {db_path} :results table :colnames yes\n"
        f"{table_query}\n"
        f"#+end_src\n"
        f"** Trends\n"
        f"#+name: trend-data\n"
        f"#+begin_src sqlite :db {db_path} :results table :colnames yes\n"
        f"{trend_query}\n"
        f"#+end_src\n"
        f"#+begin_src gnuplot :var data=trend-data :file trends.png :results graphics file :exports results\n"
        f"{gnuplot_block}\n"
        f"#+end_src"
    )


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
    config = config or {}
    display_names = config.get("display_names", {})
    babel = config.get("babel_analysis", True)
    events = db.get_all_events(conn)

    lines = []

    if babel:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        db_path = str(Path(db_path).resolve())
        start_date = config.get("sync_start", "2019-01-01")
        end_date = date.today().isoformat()
        calendar_names = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT c.summary FROM calendars c "
                "JOIN events e ON c.id = e.calendar_id "
                "WHERE e.all_day = 0 ORDER BY c.summary"
            ).fetchall()
        ]
        lines.append(_top_level_analysis(db_path, start_date, end_date, calendar_names, display_names))

    current_year = None
    current_month = None
    current_week = None
    current_day = None

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
