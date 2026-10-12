"""What makes Duplicatearr Duplicatearr: its name, port and the apps it connects to."""

import os

NAME = "Duplicatearr"
SLUG = "duplicatearr"
VERSION = "0.1.0"
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
    {"title": 'Films and episodes stored twice', "items": [
        'Groups files by their TMDB, IMDb or TVDB ID, from Radarr, Sonarr, .nfo files and folder names, so Dune (2021) and Dune Part One (2021) are seen as one film.',
        'The same film in two libraries, such as Movies and 4K, and old copies left behind after an upgrade.',
        'Episodes that exist twice, for example as both .mkv and .mp4.',
        "Checks matches by comparing frames from the video, so a 4K remux and a 1080p WEB-DL of the same film are found, and a theatrical cut isn't mistaken for the extended one.",
    ]},
    {"title": 'Posters, artwork and extras', "items": [
        'The same poster or fanart saved under different names or sizes.',
        'Trailers and extras stored more than once.',
    ]},
    {"title": 'Choosing what to keep', "items": [
        'Suggests the best copy by resolution, HDR and Dolby Vision, source and audio, which you can change.',
        'Knows which file Radarr or Sonarr tracks, so removing a copy never makes them download it again.',
    ]},
    {"title": 'Safe to leave running', "items": [
        'Report only to start with: nothing is removed until you say so.',
        'Removed files go to a recycle folder first, with restore.',
        'Files still seeding (hardlinked) are left alone until the torrent is gone.',
    ]},
]


def _default_libraries():
    """The folders mapped in the Unraid template, when they exist."""
    paths = [p.strip() for p in os.getenv("LIBRARIES", "/movies,/tv").split(",")]
    return ", ".join(p for p in paths if p and os.path.isdir(p))


def extra_fields(F, env_str, env_bool, env_int):
    return [
        F("libraries", "general", "Folders to check", "labels", _default_libraries(), section="Libraries", paths=True,
          help="Your library folders as they're mapped inside the container, separated by commas, e.g. /movies, /tv."),
    ]
