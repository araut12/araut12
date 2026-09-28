# Mission Control

A private dashboard for your OpenClaw agents that you can open from your phone or laptop anywhere. It shows:
- **Scheduled jobs**, with a **Run now** button for each
- **Recent video posts** from the video poster, with YouTube links and any errors
- **Gateway status** and the raw job list, which refresh every 30 seconds

## Start it (on the PC where OpenClaw runs)

```bash
cd mission-control
MC_TOKEN='pick-a-long-password' python3 server.py
```
Then open http://localhost:8787 on that PC.

## Open it from anywhere (Tailscale, free and private)

1. Install Tailscale on the PC (inside WSL if OpenClaw is there): https://tailscale.com/download, then run `sudo tailscale up`.
2. Install the Tailscale app on your phone and laptop, and sign in with the **same account**.
3. On the PC, run:
   ```bash
   sudo tailscale serve --bg 8787
   ```
   It prints a private HTTPS address like `https://your-pc.tailnet-name.ts.net`. Open it on your phone and add it to your home screen.

Only devices signed in to your Tailscale account can reach it, and the password adds a second lock. Don't use port forwarding or `tailscale funnel`, since those make it public.

## Keep it running after restarts (Linux/WSL)

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/mission-control.service <<UNIT
[Service]
Environment=MC_TOKEN=pick-a-long-password
ExecStart=/usr/bin/python3 $PWD/server.py
Restart=always
[Install]
WantedBy=default.target
UNIT
systemctl --user enable --now mission-control
```

## Add more agents

Edit `PANELS` at the top of `server.py`. Each entry is a title and the command whose output should be shown, for example:
```python
"Gateway logs": "openclaw logs --limit 40",
```
