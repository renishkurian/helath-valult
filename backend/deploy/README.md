# Pi deploy — systemd + nginx + Cloudflare Tunnel

This laptop is **dev only**. Install these files on the Raspberry Pi
(`nicky@raspberrypi`, app at `/var/www/python/helath-valult/backend`).

Uvicorn listens on **127.0.0.1:8076**. Nginx and the tunnel are the public
door. Android / Drive OAuth should use `https://vault.rklab.online`.

## 1. Stop the manual uvicorn

On the Pi, Ctrl+C the current `uvicorn ... --port 8076` if it is still in
the terminal.

## 2. Install the systemd service

```bash
sudo cp /var/www/python/helath-valult/backend/deploy/healthvault.service \
        /etc/systemd/system/healthvault.service
sudo systemctl daemon-reload
sudo systemctl enable --now healthvault
```

Commands:

```bash
sudo systemctl start healthvault
sudo systemctl stop healthvault
sudo systemctl restart healthvault
sudo systemctl disable healthvault    # stop auto-start on boot
sudo systemctl enable healthvault     # start on boot again
sudo systemctl status healthvault
journalctl -u healthvault -f
```

After a reboot it comes back by itself (`enable --now`).

If it fails with permission errors:

```bash
sudo chown -R nicky:nicky /var/www/python/helath-valult/backend
```

`.env` must exist on the Pi (`MASTER_KEY`, `JWT_SECRET`, `DATABASE_URL`).

## 3. Nginx reverse proxy

```bash
sudo cp /var/www/python/helath-valult/backend/deploy/nginx-vault.rklab.online.conf \
        /etc/nginx/sites-available/vault.rklab.online
sudo ln -sf /etc/nginx/sites-available/vault.rklab.online \
            /etc/nginx/sites-enabled/vault.rklab.online
sudo nginx -t && sudo systemctl reload nginx
```

## 4. Cloudflare Tunnel

In Zero Trust → Tunnels → your tunnel → Public hostname:

| Field | Value |
|---|---|
| Subdomain | `vault` |
| Domain | `rklab.online` |
| Type | HTTP |
| URL | `http://127.0.0.1:80` |

That is nginx, which then proxies to uvicorn on `8076`. Do **not** point
the tunnel straight at `8076` unless you skip nginx.

## 5. App + Drive

- Android server URL: `https://vault.rklab.online`
- Google Drive OAuth redirect (copy from Storage page after it is live):

  `https://vault.rklab.online/admin/storage/google/callback`

Want LAN access without the tunnel? Change `--host 127.0.0.1` in the
service to `--host 0.0.0.0` and `sudo systemctl restart healthvault`.
