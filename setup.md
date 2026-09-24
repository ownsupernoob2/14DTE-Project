# Smart Mirror API

This guide provides instructions for setting up and running the Smart Mirror backend server on a foreign machine using Docker. 

Once running, the machine requires zero maintenance: whenever new code is pushed to the main branch on GitHub, Watchtower automatically downloads the updated image and restarts the container.

---

## Step 1: Install Docker

If Docker is not already installed on the target machine:

### Ubuntu / Debian
Run this command in the terminal:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```
(Log out and log back in, or run `newgrp docker` so Docker can run without sudo)

### Windows and macOS
- Windows: Install Docker Desktop for Windows (ensure WSL2 is enabled).
- macOS: Install Docker Desktop for Mac.

Verify Docker is working:
```bash
docker --version
docker compose version
```

---

## Step 2: Download the Setup Files

Create a directory for the server and download the configuration files:

### Linux / macOS
```bash
mkdir -p ~/smart-mirror && cd ~/smart-mirror

curl -fsSL https://raw.githubusercontent.com/ownsupernoob2/14DTE-Project/main/server/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/ownsupernoob2/14DTE-Project/main/server/.env.example -o .env
```

### Windows (PowerShell)
```powershell
mkdir C:\smart-mirror; cd C:\smart-mirror

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/ownsupernoob2/14DTE-Project/main/server/docker-compose.yml" -OutFile "docker-compose.yml"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/ownsupernoob2/14DTE-Project/main/server/.env.example" -OutFile ".env"
```

---

## Step 3: Configure Environment Variables

Open `.env` in any text editor if changes are needed. The default configuration includes:

```ini
AUTH0_DOMAIN=dev-pgz1qjberxzo8hkl.us.auth0.com
AUTH0_AUDIENCE=https://dev-pgz1qjberxzo8hkl.us.auth0.com/api/v2/
PORT=8080
```

---

## Step 4: Start the Server

In the directory containing `docker-compose.yml`, run:

```bash
docker compose up -d
```

### What occurs:
1. Docker pulls the pre-built image `ghcr.io/ownsupernoob2/smart-mirror-api:latest`.
2. The server starts on port `8080`.
3. The `watchtower` container starts in the background to handle automated updates.
4. Persistent storage directories (`./data`, `./encodings`, `./faces`) are mounted to retain user layouts, barcodes, and face encodings.

Check container status:
```bash
docker compose ps
```

Test the health endpoint locally:
```bash
curl http://localhost:8080/health
# Response: {"status":"ok"}
```

---

## Step 5: Connecting with api.smartmirror.me

The frontend web app and physical mirror communicate with `https://api.smartmirror.me`. To route requests to port 8080:

### Option A: Server with a Public IP
1. In your DNS registrar, add an A record pointing `api.smartmirror.me` to your server's public IP address.
2. Use Caddy for automated SSL termination. Add this service to your `docker-compose.yml`:
   ```yaml
     caddy:
       image: caddy:alpine
       container_name: smart-mirror-caddy
       restart: unless-stopped
       ports:
         - "80:80"
         - "443:443"
       command: caddy reverse-proxy --from https://api.smartmirror.me --to smart-mirror-api:8080
   ```
   Or run Caddy directly on the host:
   ```bash
   sudo apt install -y caddy
   sudo caddy reverse-proxy --from https://api.smartmirror.me --to localhost:8080
   ```

### Option B: Machine Behind NAT / Router (No Public IP)
Use a Cloudflare Tunnel:
1. In Cloudflare Zero Trust Dashboard, go to Networks > Tunnels > Create Tunnel.
2. Under Public Hostnames, set:
   - Subdomain: `api`
   - Domain: `smartmirror.me`
   - Service: `HTTP` -> `localhost:8080`
3. Run the Cloudflare tunnel connector command on the host.

---

## Automated Updates

The foreign machine updates itself automatically:
1. Code changes are pushed to the `main` branch on GitHub.
2. GitHub Actions builds the new container image and pushes it to GitHub Container Registry.
3. Watchtower detects the new image within 5 minutes, pulls it down, and restarts the container with existing persistent data preserved.

---

## Helpful Commands

Run these inside the directory containing `docker-compose.yml`:

| Action | Command |
| :--- | :--- |
| Check status | `docker compose ps` |
| View server logs | `docker compose logs -f smart-mirror-api` |
| View auto-update logs | `docker compose logs -f watchtower` |
| Manually pull and restart | `docker compose pull && docker compose up -d` |
| Restart server | `docker compose restart` |
| Stop server | `docker compose down` |
| Health check | `curl http://localhost:8080/health` |
