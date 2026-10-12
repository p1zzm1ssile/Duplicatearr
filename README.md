<p align="center"><img src="src/web/logo.png" alt="Duplicatearr" width="280"></p>

# Duplicatearr

Finds the same film, episode, poster or extra stored more than once in your library, even when the copies are different encodes, and helps you keep the best one.

> **Early version.** The web UI, login and connections to Radarr, Sonarr, Jellyfin and Plex work today. The checks below are being built and
> will arrive in the next releases. Watch or star the repository to hear when they land.

## What it will check

### Films and episodes stored twice

- Groups files by their TMDB, IMDb or TVDB ID, from Radarr, Sonarr, .nfo files and folder names, so Dune (2021) and Dune Part One (2021) are seen as one film.
- The same film in two libraries, such as Movies and 4K, and old copies left behind after an upgrade.
- Episodes that exist twice, for example as both .mkv and .mp4.
- Checks matches by comparing frames from the video, so a 4K remux and a 1080p WEB-DL of the same film are found, and a theatrical cut isn't mistaken for the extended one.

### Posters, artwork and extras

- The same poster or fanart saved under different names or sizes.
- Trailers and extras stored more than once.

### Choosing what to keep

- Suggests the best copy by resolution, HDR and Dolby Vision, source and audio, which you can change.
- Knows which file Radarr or Sonarr tracks, so removing a copy never makes them download it again.

### Safe to leave running

- Report only to start with: nothing is removed until you say so.
- Removed files go to a recycle folder first, with restore.
- Files still seeding (hardlinked) are left alone until the torrent is gone.

## Install on Unraid

1. Add the template from [`unraid/duplicatearr.xml`](unraid/duplicatearr.xml), or search Community Apps for Duplicatearr.
2. Keep the **Config** folder at `/mnt/user/appdata/duplicatearr`.
3. Map **Movies** to your movies folder, read/write. Map the same folder Radarr uses, so the paths match.
3. Map **TV** to your tv folder, read/write. Map the same folder Sonarr uses, so the paths match.
5. Start it, open the web UI (port 9894), and create your login with the setup code from the container's log.
6. Add your apps under **Settings** and press **Test connection** on each.

## Install with Docker

```bash
docker run -d --name duplicatearr \
  -p 9894:9894 \
  -v /path/to/appdata/duplicatearr:/config \
  -v /path/to/movies:/movies \
  -v /path/to/tv:/tv \
  ghcr.io/p1zzm1ssile/duplicatearr:latest
```

Or with Docker Compose:

```yaml
services:
  duplicatearr:
    image: ghcr.io/p1zzm1ssile/duplicatearr:latest
    container_name: duplicatearr
    ports:
      - 9894:9894
    volumes:
      - ./duplicatearr:/config
      - /path/to/movies:/movies
      - /path/to/tv:/tv
    restart: unless-stopped
```

Every setting is in the web UI. To pre-fill them on first start, see `.env.tmpl` for the environment variables.

## First run

1. Open `http://your-server:9894`.
2. Enter the **setup code** from Duplicatearr's log. It's printed when Duplicatearr starts (in Unraid, click the Duplicatearr icon and
   choose **Logs**; with Docker, run `docker logs duplicatearr`). This stops anyone else on your network, or anyone reaching
   it through a misconfigured proxy, from creating the account before you.
3. Create your login. The password needs at least 8 characters, with an uppercase letter, a lowercase letter, a number
   and a special character.

## Login and security

> ⚠️ **Keep Duplicatearr on your home network.** It can delete files from your library and holds your Radarr, Sonarr, Jellyfin and Plex keys. We don't recommend putting it behind a reverse proxy
> (Nginx Proxy Manager, SWAG, Traefik, Cloudflare Tunnel and the like) for access from outside your network. To reach
> it remotely, use a VPN such as WireGuard or Tailscale.

- The password is stored as a scrypt hash in `/config/auth.json`, never in plain text.
- After 5 wrong passwords, that address is locked out for 5 minutes.
- **Skip login on my local network** (Settings > General) lets devices on the networks you list in without a password.
  It never applies to requests that arrive through a reverse proxy.
- Changing an app's address needs its API key entered again, so a saved key can't be sent somewhere new.
- Saved API keys are never sent back to the browser, and `settings.json` and `auth.json` are only readable by the
  account Duplicatearr runs as.
- **Forgotten your password?** Delete `auth.json` from the config folder and restart Duplicatearr. It will ask you to create
  a login again, with a new setup code in the log. Your settings are kept.

## Health check

- **HTTP:** `GET /health` returns the status as JSON, with HTTP 200 when healthy and 503 when not.
- **Command line:** `docker exec duplicatearr python healthcheck.py` exits with 0 when healthy, 1 when not.
- **Docker:** the image includes a `HEALTHCHECK`, so `docker ps` shows `healthy` or `unhealthy`.

## Contact

Bugs and ideas: [open an issue](https://github.com/p1zzm1ssile/Duplicatearr/issues/new?title=%5BDuplicatearr%5D%20). For anything
private, email [p1zzm1ssilerepo@gmail.com](mailto:p1zzm1ssilerepo@gmail.com?subject=Duplicatearr). Both are also on the Contact page in the web UI.

## Licence

MIT. See [LICENSE](LICENSE).
