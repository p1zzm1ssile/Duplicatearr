# Changelog

## 0.2.1

- **Much faster artwork check.** It could take hours on a big library. Episode thumbnails are now skipped (each is a
  different episode), a picture is only read when another in its folder has the same shape, JPEGs are read at a
  fraction of their size, a few are read at a time, and results are saved in batches.
- Extras are only read when two in the same folder are exactly the same size.
- Every step of a scan shows its own progress, and **Stop** works in all of them.
- The log says when a scan starts, how long each step took, and when it finishes or is stopped.

## 0.2.0

- **Scan now** finds films and episodes stored more than once, by TMDB, IMDb or TVDB ID (folder names and .nfo
  files) or title and year, across all your libraries.
- Each copy is read with ffprobe and frames are compared, so mislabelled files, different editions and different cuts
  aren't ticked for removal.
- The best copy is suggested to keep, or the one Radarr or Sonarr tracks.
- Also finds identical extras and the same picture saved twice.
- Ticked copies move to a recycle folder with their subtitles and artwork, and can be restored from History.
  They're emptied after 7 days (Settings).
- Scans run once a day by themselves, and at low priority.
- Jellyfin 10.11 no longer turns down the API key.

## 0.1.0

- First release: web UI with login, Dashboard, Logs, Settings and Contact pages.
- Connections to each app, with **Test connection**.
- Health check in the web UI, at `/health`, and as a Docker health check.
- The Dashboard lists the checks coming in the next releases.
