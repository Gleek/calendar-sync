from datetime import datetime, timezone
from googleapiclient.errors import HttpError

from . import db


def parse_event_time(time_dict):
    """Parse Google Calendar time object. Returns (iso_string, is_all_day)."""
    if "dateTime" in time_dict:
        return time_dict["dateTime"], False
    if "date" in time_dict:
        return time_dict["date"], True
    raise ValueError(f"Unexpected time format: {time_dict}")


def compute_duration_minutes(start_str, end_str, all_day):
    if all_day:
        # all-day events: count days * 24 * 60
        from datetime import date as date_type

        start = date_type.fromisoformat(start_str)
        end = date_type.fromisoformat(end_str)
        return (end - start).days * 24 * 60
    start = datetime.fromisoformat(start_str)
    end = datetime.fromisoformat(end_str)
    return int((end - start).total_seconds() / 60)


def event_to_row(event, calendar_id):
    """Convert a Google Calendar API event dict to a db row dict."""
    start_str, all_day = parse_event_time(event["start"])
    end_str = None
    duration = None
    if "end" in event:
        end_str, _ = parse_event_time(event["end"])
        duration = compute_duration_minutes(start_str, end_str, all_day)

    return {
        "id": event["id"],
        "calendar_id": calendar_id,
        "summary": event.get("summary"),
        "description": event.get("description"),
        "location": event.get("location"),
        "start_time": start_str,
        "end_time": end_str,
        "duration_minutes": duration,
        "all_day": 1 if all_day else 0,
        "recurring_event_id": event.get("recurringEventId"),
        "status": event.get("status", "confirmed"),
        "created": event.get("created"),
        "updated": event.get("updated"),
    }


def _sync_calendar_full(service, conn, calendar_id, time_min, time_max):
    """Full sync with singleEvents=True to expand recurrences."""
    event_count = 0
    page_token = None

    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
                pageToken=page_token,
            )
            .execute()
        )

        for event in response.get("items", []):
            if event.get("status") == "cancelled":
                db.delete_event(conn, event["id"], calendar_id)
            else:
                db.upsert_event(conn, event_to_row(event, calendar_id))
            event_count += 1

        page_token = response.get("nextPageToken")
        if not page_token:
            sync_token = response.get("nextSyncToken")
            break

    # Full sync with singleEvents=True doesn't return a usable sync token
    # for incremental sync (which requires singleEvents=False).
    # Do a no-op list call without singleEvents to get a valid sync token.
    token_response = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=1,
        )
        .execute()
    )
    # Drain pages to get final sync token
    while token_response.get("nextPageToken"):
        token_response = (
            service.events()
            .list(
                calendarId=calendar_id,
                pageToken=token_response["nextPageToken"],
            )
            .execute()
        )
    sync_token = token_response.get("nextSyncToken")

    if sync_token:
        db.set_sync_token(conn, calendar_id, sync_token)

    return event_count


def _expand_recurring_instances(service, conn, calendar_id, recurring_event_id,
                                time_min, time_max):
    """Fetch all instances of a recurring event and upsert them."""
    count = 0
    page_token = None

    while True:
        try:
            response = (
                service.events()
                .instances(
                    calendarId=calendar_id,
                    eventId=recurring_event_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=2500,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError:
            # Event may have been deleted
            break

        for instance in response.get("items", []):
            if instance.get("status") == "cancelled":
                db.delete_event(conn, instance["id"], calendar_id)
            else:
                db.upsert_event(conn, event_to_row(instance, calendar_id))
            count += 1

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return count


def _sync_calendar_incremental(service, conn, calendar_id, sync_token,
                               time_min, time_max):
    """Incremental sync using sync token. Returns (event_count, success).
    If sync token is rejected (410), returns (0, False)."""
    event_count = 0
    page_token = None

    try:
        while True:
            response = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    syncToken=sync_token,
                    maxResults=2500,
                    pageToken=page_token,
                )
                .execute()
            )

            for event in response.get("items", []):
                if event.get("status") == "cancelled":
                    db.delete_event(conn, event["id"], calendar_id)
                    event_count += 1
                elif "recurrence" in event:
                    db.delete_events_by_recurring_id(
                        conn, event["id"], calendar_id
                    )
                    count = _expand_recurring_instances(
                        service, conn, calendar_id, event["id"],
                        time_min, time_max,
                    )
                    event_count += count
                else:
                    # Skip future events on incremental sync too
                    row = event_to_row(event, calendar_id)
                    if row["start_time"] <= time_max:
                        db.upsert_event(conn, row)
                    event_count += 1

            page_token = response.get("nextPageToken")
            if not page_token:
                new_token = response.get("nextSyncToken")
                if new_token:
                    db.set_sync_token(conn, calendar_id, new_token)
                break

    except HttpError as e:
        if e.resp.status == 410:
            return 0, False
        raise

    return event_count, True


def sync_calendars(service, conn):
    """Sync calendar list from Google."""
    calendars = []
    page_token = None

    while True:
        response = (
            service.calendarList()
            .list(maxResults=250, pageToken=page_token)
            .execute()
        )

        for cal in response.get("items", []):
            cal_row = {
                "id": cal["id"],
                "summary": cal.get("summary", ""),
                "description": cal.get("description"),
                "time_zone": cal.get("timeZone"),
                "color": cal.get("backgroundColor"),
            }
            db.upsert_calendar(conn, cal_row)
            calendars.append(cal_row)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    conn.commit()
    return calendars


def sync_all(service, conn, config, full=False):
    """Sync all calendars and their events."""
    calendars = sync_calendars(service, conn)

    whitelist = set(config.get("calendars", []))
    sync_start = config.get("sync_start", "2019-01-01")
    time_min = f"{sync_start}T00:00:00Z"
    time_max = datetime.now(timezone.utc).isoformat()

    if whitelist:
        skipped = [c["summary"] for c in calendars if c["summary"] not in whitelist]
        calendars = [c for c in calendars if c["summary"] in whitelist]
        if skipped:
            print(f"  Skipping: {', '.join(skipped)}")

    total_events = 0
    for cal in calendars:
        calendar_id = cal["id"]
        calendar_name = cal["summary"]

        if not full:
            sync_token = db.get_sync_token(conn, calendar_id)
        else:
            sync_token = None

        if sync_token:
            count, success = _sync_calendar_incremental(
                service, conn, calendar_id, sync_token,
                time_min, time_max,
            )
            if not success:
                count = _sync_calendar_full(
                    service, conn, calendar_id, time_min, time_max
                )
            sync_type = "incremental" if success else "full (token expired)"
        else:
            count = _sync_calendar_full(
                service, conn, calendar_id, time_min, time_max
            )
            sync_type = "full"

        print(f"  {calendar_name}: {count} events ({sync_type})")
        total_events += count
        conn.commit()

    return len(calendars), total_events
