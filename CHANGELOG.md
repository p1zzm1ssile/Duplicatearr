# Changelog

## Unreleased

- **Episodes named in words are episodes.** `Show Season 05 Episode 01.mkv` (or `Series 5 Ep 1`), and `Episode 01.mkv`
  in a season folder like `S05` or `Season 5`, weren't recognised, so a season's episodes were grouped as one film
  named after the folder. They're now read as episodes, and any other video under a season folder is treated as an
  extra rather than a film.
- **Two files Radarr or Sonarr track aren't duplicates.** They keep one file per film or episode, so two tracked files
  under one episode number (specials that share a slot, say) are left alone.
- **Pictures named after their folder are artwork.** `'Allo 'Allo!/'Allo 'Allo!.jpg` beside `poster.jpg` and
  `folder.jpg`, or `Dune (2021).jpg` beside `Dune (2021).mkv`, is there on purpose and no longer listed.
- **Identical extras are checked all the way through** before one is ticked, not just their size, start and end.
- **Keys and passwords are kept out of the logs.** Any API key or password, and any `apikey=`, `token=` or `password=` in a web address quoted by an error, is replaced by `***` before it's written. Log files, and the file that holds the login, can now only be read by the account the app runs as.
- **The dashboard shows 50 groups at a time**, with a Show more button. A big library could list tens of thousands
  and freeze the browser.
- **Far fewer pictures listed.** Copies that all have names players look for (`poster.jpg`, `folder.jpg`,
  `Film-poster.jpg`, `fanart.jpg` and so on) are there on purpose and are no longer listed. A copy under any other
  name, like `poster (1).jpg`, still is.
- **Openings, endings and specials aren't films.** Videos in a series' folder without an episode number (`OP.mkv`,
  `ED.mkv`, `Special 01.mkv`) were grouped as one film. They're now treated as extras: only identical copies are listed.

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
