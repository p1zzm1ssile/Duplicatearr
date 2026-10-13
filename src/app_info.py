"""What makes Duplicatearr Duplicatearr: its name, port and the apps it connects to."""

import os

NAME = "Duplicatearr"
SLUG = "duplicatearr"
VERSION = "0.2.1"
PORT = 9894
TAGLINE = 'Finds the same film, episode, poster or extra stored more than once in your library, even when the copies are different encodes, and helps you keep the best one.'

# (key, name, default port, where to find the API key)
SERVICES = [
    ("radarr", "Radarr", 7878, 'Settings > General > Security in Radarr'),
    ("sonarr", "Sonarr", 8989, 'Settings > General > Security in Sonarr'),
    ("jellyfin", "Jellyfin", 8096, 'Dashboard > API Keys in Jellyfin'),
    ("plex", "Plex", 32400, 'Your Plex token. Plex\'s support article "Finding an authentication token" shows where to find it.'),
]

# Shown on the Dashboard until each check is ready
PLANNED = [
    {"title": "Coming next", "items": [
        "Your own rules, such as always keeping the 4K copy, applied by themselves once you trust them.",
        "Telling Jellyfin and Plex straight away when a copy is removed.",
        "Duplicate music and books.",
    ]},
]


def _default_libraries():
    """The folders mapped in the Unraid template, when they exist."""
    paths = [p.strip() for p in os.getenv("LIBRARIES", "/movies,/tv").split(",")]
    return ", ".join(p for p in paths if p and os.path.isdir(p))


def extra_fields(F, env_str, env_bool, env_int):
    return [
        F("libraries", "general", "Folders to check", "labels", _default_libraries(), section="Libraries", paths=True,
          help="Your library folders as they're mapped inside the container, separated by commas, e.g. /movies, /tv. "
               "Films and episodes are told apart by their names, so one folder can hold both."),
        F("scan_interval_hours", "general", "Scan every (hours)", "int", env_int("SCAN_INTERVAL_HOURS", default=24),
          section="Scanning", min=1, max=720,
          help="Scans only report what they find. Nothing is ever removed until you tick it and press the button."),
        F("check_images", "general", "Look for duplicate posters and artwork", "bool",
          env_bool("CHECK_IMAGES", default=True), section="Scanning",
          help="The same picture saved twice in one folder under different names or sizes."),
        F("compare_frames", "general", "Compare frames from the video", "bool", env_bool("COMPARE_FRAMES", default=True),
          section="Scanning",
          help="Takes a few frames from each copy to check they're the same film or episode before suggesting one "
               "for removal. Uses a little CPU on files that look like duplicates; nothing else is read."),
        F("low_priority", "general", "Run at low priority", "bool", env_bool("LOW_PRIORITY", default=True),
          section="Scanning", help="ffprobe and ffmpeg give way to everything else on the server, like a Jellyfin transcode."),
        F("recycle_days", "general", "Keep removed files for (days)", "int", env_int("RECYCLE_DAYS", default=7),
          section="Recycle folder", min=0, max=365,
          help="Removed copies can be restored from History until then. 0 deletes them straight away."),
        F("recycle_folder", "general", "Recycle folder", "text", env_str("RECYCLE_FOLDER", default=""),
          section="Recycle folder", paths=True,
          help="Leave empty to use a hidden .duplicatearr-recycle folder at the top of each library, which keeps "
               "removed files on the same disk so moving them is instant."),
    ]
