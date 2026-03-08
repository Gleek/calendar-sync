import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "calsync"


def get_credentials(config_dir=None):
    config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)

    token_path = config_dir / "token.json"
    credentials_path = config_dir / "credentials.json"

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Place your Google OAuth client credentials at {credentials_path}\n"
            "Download from: Google Cloud Console → APIs & Services → Credentials → "
            "OAuth 2.0 Client IDs → Download JSON"
        )

    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path), SCOPES
        )
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


def build_service(creds):
    return build("calendar", "v3", credentials=creds)
