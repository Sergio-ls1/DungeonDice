# Deployment Instructions — Dungeon Dice Multiplayer Server

This document explains how to deploy the FastAPI WebSocket server (`server_app.py`) to the cloud (Render or Railway) so players can connect from anywhere on the internet.

---

## 1. Prerequisites
Ensure your repository contains the following files in the root folder:
- `requirements.txt`:
  ```text
  fastapi
  uvicorn
  websockets
  ```
- `dungeon_dice/network/server_app.py`
- `dungeon_dice/network/room_manager.py`
- `dungeon_dice/network/network_models.py`

---

## 2. Deploying on Render

Render is a free-tier hosting service that is ideal for hosting FastAPI servers.

### Step-by-Step:
1. Log into [Render](https://render.com/).
2. Click **New +** and select **Web Service**.
3. Connect your GitHub repository containing the DungeonDice codebase.
4. Configure the Web Service settings:
   - **Name**: `dungeondice-server` (or any custom name)
   - **Environment**: `Python`
   - **Region**: Select the region closest to your players
   - **Branch**: `main` (or your active development branch)
5. Build and Start commands:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m uvicorn dungeon_dice.network.server_app:app --host 0.0.0.0 --port $PORT`
6. Click **Create Web Service**.
7. Once Render builds and deploys your service, it will provide a public URL like:
   `https://dungeondice-server.onrender.com`

---

## 3. Deploying on Railway

Railway is a cloud deployment platform that supports fast setups.

### Step-by-Step:
1. Log into [Railway](https://railway.app/).
2. Click **New Project** and select **Deploy from GitHub repo**.
3. Choose your project repository.
4. Go to **Variables** on the Railway panel and define:
   - `PORT`: `8000` (or Railway will assign one dynamically)
5. Go to **Settings** and set the Start Command:
   - **Start Command**: `python -m uvicorn dungeon_dice.network.server_app:app --host 0.0.0.0 --port $PORT`
6. railway will build and launch the server automatically.
7. Under **Settings**, generate a Domain under the **Domains** section to receive a public URL like:
   `https://your-service-name.up.railway.app`

---

## 4. Connecting the Client App
Once your server is online:
1. Copy the public URL (e.g. `https://dungeondice-server.onrender.com`).
2. Replace `https://` with `wss://` (e.g. `wss://dungeondice-server.onrender.com`).
3. Update [config/network.json](file:///c:/SISTEMAS%20OPERATIVOS/JUEGO_ROLES_PYTHON/config/network.json) on all client machines:
   ```json
   {
     "server_url": "wss://dungeondice-server.onrender.com"
   }
   ```
4. Build the standalone executable again using `build.bat`.
5. Distribute `DungeonDice.exe` to your players. They can now join and play from different cities and networks.
