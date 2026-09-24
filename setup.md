## Step 1: Install Docker

If Docker is not already installed on the target machine:

### Ubuntu / Debian (Recommended for cloud servers)
Run this single command in your terminal:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```
*(Log out and log back in, or run `newgrp docker` so you can run Docker without `sudo`)*

### Windows & macOS
- **Windows**: Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) (ensure WSL2 is enabled).
- **macOS**: Download and install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/).

Verify Docker is working by opening a terminal/PowerShell and running:
```bash
docker --version
docker compose version
```

---

## Step 2: Download the Setup Files

Create a dedicated folder for the server and download the configuration files:

### Linux / macOS (Terminal)
```bash
mkdir -p ~/smart-mirror && cd ~/smart-mirror

# Download docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/ownsupernoob2/14DTE-Project/main/server/docker-compose.yml -o docker-compose.yml

# Download environment template
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

Open the `.env` file in any text editor (e.g. `nano .env` or Notepad).

The default values are already configured for the Smart Mirror project:
```ini
AUTH0_DOMAIN=dev-pgz1qjberxzo8hkl.us.auth0.com
AUTH0_AUDIENCE=https://dev-pgz1qjberxzo8hkl.us.auth0.com/api/v2/
PORT=8080
```
Save and close the file.

> [!IMPORTANT]
> **GitHub Package Visibility**: In GitHub, make sure the package `ghcr.io/ownsupernoob2/smart-mirror-api` has its visibility set to **Public** (under GitHub Profile -> Packages -> `smart-mirror-api` -> Package Settings -> Change visibility to Public). This allows the machine to pull the pre-built image without needing private login credentials.

---

## Step 4: Start the Server (1 Command)

In the directory containing `docker-compose.yml`, run:

```bash
docker compose up -d
```

### What happens now:
1. Docker pulls the pre-built image `ghcr.io/ownsupernoob2/smart-mirror-api:latest`.
2. The server starts on port `8080`.
3. The `watchtower` container starts in the background.
4. Local storage folders (`./data`, `./encodings`, `./faces`) are automatically created.

Check that everything is running:
```bash
docker compose ps
```

Test the health check locally:
```bash
curl http://localhost:8080/health
# Output: {"status":"ok"}
```

---

## Step 5: Connecting with `api.smartmirror.me`

The web dashboard (`smartmirror.me`) and the smart mirror client make requests to `https://api.smartmirror.me`. 

To connect `api.smartmirror.me` to your Docker container on port `8080`:

### Option A: Cloud Server / VPS with a Public IP (DigitalOcean, AWS, Linode, etc.)
1. **DNS**: In your domain registrar (e.g., Namecheap or Cloudflare), create an **A Record**:
   - **Type**: `A`
   - **Name / Host**: `api`
   - **Value / Target**: `<Your-Server-Public-IP>`
2. **Automatic SSL Reverse Proxy with Caddy**:
   Caddy automatically provisions and renews SSL certificates from Let's Encrypt with zero manual configuration.
   
   You can add Caddy directly to your `docker-compose.yml`:
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
   Or install Caddy directly on the host:
   ```bash
   sudo apt install -y caddy
   sudo caddy reverse-proxy --from https://api.smartmirror.me --to localhost:8080
   ```

### Option B: Home / School Machine (Behind Router / NAT / No Public IP)
If the machine is running in a home or school network without a static public IP or port forwarding, use a **Cloudflare Tunnel** (free, secure, and provides automated HTTPS):
1. In the [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/), go to **Networks** > **Tunnels** > **Create Tunnel**.
2. Name it `smart-mirror-tunnel`.
3. In Public Hostnames:
   - **Subdomain**: `api`
   - **Domain**: `smartmirror.me`
   - **Service**: `HTTP` -> `localhost:8080` (or `smart-mirror-api:8080` in Docker)
4. Cloudflare will give you a simple 1-line Docker command to run the tunnel on the machine.

---

## How Remote Updates Work (Hands-Off)

You do **not** need to touch this foreign machine when pushing code updates!

1. You edit code and push to the `main` branch on GitHub:
   ```bash
   git commit -m "Update API feature"
   git push origin main
   ```
2. GitHub Actions detects changes in `server/`, builds the new Docker image, and pushes it to `ghcr.io/ownsupernoob2/smart-mirror-api:latest`.
3. Within 5 minutes, **Watchtower** on the foreign machine notices the new image, pulls it down, and restarts the container gracefully.
4. All user data, barcodes, and face encodings remain safe in `./data` and `./encodings`.

---

## Helpful Commands Cheat Sheet

Run these in the folder containing `docker-compose.yml`:

| Action | Command |
| :--- | :--- |
| **Check container status** | `docker compose ps` |
| **View live server logs** | `docker compose logs -f smart-mirror-api` |
| **View auto-update logs** | `docker compose logs -f watchtower` |
| **Manually trigger an update** | `docker compose pull && docker compose up -d` |
| **Restart the server** | `docker compose restart` |
| **Stop the server** | `docker compose down` |
| **Check server health** | `curl http://localhost:8080/health` |
