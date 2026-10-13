"""Walking the libraries and working out what each file is.

A film is known by its folder: the TMDB or IMDb ID in the folder name (Radarr's
{tmdb-123} or Jellyfin's [tmdbid-123]) or in its .nfo file, and otherwise its
title and year. An episode is known by its series folder (a TVDB ID, or the
title) plus the season and episode numbers in its file name.
"""

import os
import re
from dataclasses import dataclass, field

VIDEO = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".m2ts", ".mpg", ".mpeg", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".tbn"}
RECYCLE_NAME = ".duplicatearr-recycle"

# Folders and name endings Plex, Jellyfin and Kodi use for extras
EXTRAS_FOLDERS = {"extras", "featurettes", "behind the scenes", "deleted scenes", "interviews", "scenes", "shorts",
                  "trailers", "other", "others", "sample", "samples", "clips", "bonus", "specials features"}
EXTRAS_SUFFIX = re.compile(
    r"[-._ ](trailer|sample|featurette|behindthescenes|deleted|deletedscene|interview|scene|short|other|extra|clip)\d*$",
    re.I)

EPISODE = re.compile(r"(?<![a-z0-9])s(\d{1,3})[ ._-]?e(\d{1,4})((?:[ ._-]?-?e\d{1,4})*)", re.I)
EPISODE_X = re.compile(r"(?<![a-z0-9])(\d{1,2})x(\d{2,3})(?![0-9])", re.I)
MORE_EPISODES = re.compile(r"e(\d{1,4})", re.I)
YEAR = re.compile(r"\((\d{4})\)|[. _\[](19\d{2}|20\d{2})(?:[. _\])]|$)")
TMDB = re.compile(r"[\[{(](?:tmdb|tmdbid)[-=](\d+)[\]})]", re.I)
IMDB = re.compile(r"[\[{(](?:imdb|imdbid)[-=](tt\d+)[\]})]", re.I)
TVDB = re.compile(r"[\[{(](?:tvdb|tvdbid)[-=](\d+)[\]})]", re.I)
NFO_TMDB = re.compile(r'<uniqueid[^>]*type="tmdb"[^>]*>\s*(\d+)\s*<|<tmdbid>\s*(\d+)\s*<', re.I)
NFO_IMDB = re.compile(r"(tt\d{5,})")
NFO_TVDB = re.compile(r'<uniqueid[^>]*type="tvdb"[^>]*>\s*(\d+)\s*<|<tvdbid>\s*(\d+)\s*<', re.I)
EDITION_TAG = re.compile(r"\{edition-([^}]+)\}", re.I)
EDITION_WORDS = re.compile(
    r"(?<![a-z])(extended(?: cut| edition)?|director'?s(?: cut)?|unrated|uncut|theatrical(?: cut)?|imax|final cut|"
    r"special edition|ultimate(?: cut| edition)?|remastered)(?![a-z])", re.I)
PART = re.compile(r"(?<![a-z])(?:cd|disc|disk|dvd|part|pt)[ ._-]?(\d{1,2})(?![0-9])", re.I)


@dataclass
class MediaFile:
    path: str
    size: int
    library: str
    kind: str                     # "movie", "episode", "extra"
    key: str = ""                 # what it is: a film's or an episode's identity
    title: str = ""               # for people: "Dune (2021)" or "Breaking Bad S01E03"
    edition: str = ""
    part: str = ""
    inode: tuple = ()
    links: int = 1
    ids: dict = field(default_factory=dict)
    episodes: list = field(default_factory=list)  # [(season, episode)] for an episode file


def clean_title(name):
    """"Dune Part One (2021) {tmdb-438631}" -> "Dune Part One"."""
    name = re.sub(r"[\[{(][^\]})]*[\]})]", " ", name)
    name = re.sub(r"[._]+", " ", name)
    return re.sub(r"\s+", " ", name).strip(" -")


def title_key(name):
    year = YEAR.search(name)
    # Only the title before the year: "Dune.2021.2160p.WEB-DL" -> "Dune"
    base = name[:year.start()] if year and year.start() > 0 else name
    title = re.sub(r"[^a-z0-9]", "", clean_title(base).lower().replace("&", "and"))
    title = re.sub(r"^the", "", title)
    return f"title:{title}|{(year.group(1) or year.group(2)) if year else ''}"


def read_nfo(folder, names):
    ids = {}
    for name in names:
        if not name.lower().endswith(".nfo"):
            continue
        try:
            with open(os.path.join(folder, name), errors="replace") as f:
                text = f.read(200_000)
        except OSError:
            continue
        for key, pattern in (("tmdb", NFO_TMDB), ("tvdb", NFO_TVDB)):
            match = pattern.search(text)
            if match and key not in ids:
                ids[key] = next(g for g in match.groups() if g)
        match = NFO_IMDB.search(text)
        if match and "imdb" not in ids:
            ids["imdb"] = match.group(1)
    return ids


def ids_from_name(name):
    ids = {}
    for key, pattern in (("tmdb", TMDB), ("imdb", IMDB), ("tvdb", TVDB)):
        match = pattern.search(name)
        if match:
            ids[key] = match.group(1)
    return ids


def edition_of(name):
    tag = EDITION_TAG.search(name)
    if tag:
        return tag.group(1).strip().lower()
    words = EDITION_WORDS.search(name.replace(".", " ").replace("_", " "))
    return re.sub(r"\s+", " ", words.group(1).lower().replace("'", "")) if words else ""


def episodes_in(name):
    """[(season, episode), ...] from a file name, or []."""
    match = EPISODE.search(name)
    if match:
        season = int(match.group(1))
        numbers = [int(match.group(2))] + [int(n) for n in MORE_EPISODES.findall(match.group(3) or "")]
        if len(numbers) == 2 and "-" in (match.group(3) or "") and numbers[1] > numbers[0]:
            numbers = list(range(numbers[0], numbers[1] + 1))  # S01E01-E03
        return [(season, n) for n in numbers]
    match = EPISODE_X.search(name)
    if match:
        return [(int(match.group(1)), int(match.group(2)))]
    return []


def is_extra(relative_parts, stem):
    return any(p.lower() in EXTRAS_FOLDERS for p in relative_parts[:-1]) or bool(EXTRAS_SUFFIX.search(stem))


def walk(libraries, stop=lambda: False, found=lambda: None):
    """Every video and image under the libraries, as (MediaFile list, images by folder)."""
    videos, images = [], {}
    nfo_cache = {}

    def folder_ids(folder):
        if folder not in nfo_cache:
            try:
                names = os.listdir(folder)
            except OSError:
                names = []
            nfo_cache[folder] = {**read_nfo(folder, names), **ids_from_name(os.path.basename(folder))}
        return nfo_cache[folder]

    for library in libraries:
        for folder, dirs, files in os.walk(library):
            if stop():
                return videos, images
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("@eaDir", "#recycle", "lost+found")]
            for name in files:
                stem, ext = os.path.splitext(name)
                ext = ext.lower()
                path = os.path.join(folder, name)
                if ext in IMAGE:
                    images.setdefault(folder, []).append(path)
                    found()
                    continue
                if ext not in VIDEO:
                    continue
                found()
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                relative = os.path.relpath(path, library).split(os.sep)
                f = MediaFile(path=path, size=st.st_size, library=library, kind="movie",
                              inode=(st.st_dev, st.st_ino), links=st.st_nlink)
                if is_extra(relative, stem):
                    f.kind = "extra"
                    f.key = "extra:" + folder
                    f.title = os.path.relpath(folder, library)
                    videos.append(f)
                    continue
                episodes = episodes_in(name)
                if episodes and len(relative) >= 2:
                    series_folder = os.path.join(library, relative[0])
                    ids = folder_ids(series_folder)
                    series = f"tvdb:{ids['tvdb']}" if "tvdb" in ids else title_key(relative[0])
                    f.kind = "episode"
                    f.ids = ids
                    f.key = series
                    f.title = clean_title(relative[0])
                    f.episodes = episodes
                    videos.append(f)
                    continue
                movie_folder = folder if len(relative) >= 2 else path
                f.ids = folder_ids(folder) if len(relative) >= 2 else ids_from_name(name)
                named = os.path.basename(movie_folder) if len(relative) >= 2 else stem
                year = YEAR.search(named)
                f.title = clean_title(named[:year.start()] if year and year.start() > 0 else named)
                if year:
                    f.title += f" ({year.group(1) or year.group(2)})"
                f.edition = edition_of(name) or edition_of(os.path.basename(folder))
                part = PART.search(stem)
                f.part = part.group(1).lstrip("0") if part else ""
                f.key = title_key(os.path.basename(movie_folder) if len(relative) >= 2 else stem)
                videos.append(f)
    return videos, images


def group_movies(movies):
    """{identity: [MediaFile]} for films, joining folders that share a TMDB or IMDb ID or a title and year.

    A folder with only a title joins one with an ID when the title and year match, unless that title and year
    belong to more than one ID (a remake in the same year, say).
    """
    by_id, title_only = {}, []
    title_to_ids = {}
    for f in movies:
        ident = f"tmdb:{f.ids['tmdb']}" if "tmdb" in f.ids else f"imdb:{f.ids['imdb']}" if "imdb" in f.ids else None
        if ident:
            by_id.setdefault(ident, []).append(f)
            title_to_ids.setdefault(f.key, set()).add(ident)
        else:
            title_only.append(f)
    # Join IMDb-only groups to TMDB groups that share a title
    groups = dict(by_id)
    for f in title_only:
        ids = title_to_ids.get(f.key, set())
        target = next(iter(ids)) if len(ids) == 1 else f.key
        groups.setdefault(target, []).append(f)
    return groups


def group_episodes(episodes):
    """{identity: [MediaFile]} for each season and episode, including every episode a multi-episode file covers."""
    groups = {}
    for f in episodes:
        for season, episode in f.episodes:
            groups.setdefault(f"{f.key}|S{season:02d}E{episode:02d}", []).append(f)
    return groups
