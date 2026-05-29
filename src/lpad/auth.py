"""Launchpad authentication via launchpadlib OAuth."""

import os

from launchpadlib.credentials import UnencryptedFileCredentialStore
from launchpadlib.launchpad import Launchpad

APP_NAME = "lpad"
LAUNCHPAD_URL = "production"
CREDENTIALS_FILE = os.path.expanduser("~/.lpadlib/lpad-credentials")


def get_launchpad() -> Launchpad:
    """Return an authenticated Launchpad instance.

    On first run, opens a browser for OAuth authorization and caches
    credentials to ~/.lpadlib/lpad-credentials as a plain file.
    Subsequent calls reuse cached credentials without prompting.
    """
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    return Launchpad.login_with(
        APP_NAME,
        LAUNCHPAD_URL,
        version="devel",
        credential_store=UnencryptedFileCredentialStore(CREDENTIALS_FILE),
    )
