# Quick Start Guide

Get the AI Security System up and running in minutes.

## Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available

## Quick Deployment

### 1. Navigate to Deployment Directory

### 2. Verify Environment Files Exist

```bash
ls -la *.env
```

You should see:
- `celery-worker.env`
- `classification-service.env`
- `tracking-service.env`
- `pipeline-service.env`
- `event-processor.env`
- `master-service.env`

need to replace credential values in env files with real values

### 3. Build and Start Services

#### Option A: Build and Run Locally

```bash
# Build all Docker images
docker compose build

# Start all services
docker compose up -d
```

#### Option B: Build and Transfer to Server (Without Registry)

If deploying to a remote server without Docker registry:

```bash
# 1. Build images locally
docker compose build --no-cache

# 2. Save images to tar files
docker save be-master-service:latest | gzip > be-master-service.tar.gz
docker save be-celery-worker:latest | gzip > be-celery-worker.tar.gz
docker save be-event-processor:latest | gzip > be-event-processor.tar.gz
docker save be-classification-service:latest | gzip > be-classification-service.tar.gz
docker save be-tracking-service:latest | gzip > be-tracking-service.tar.gz
docker save be-pipeline-service:latest | gzip > be-pipeline-service.tar.gz

# 3. Transfer to server
scp be-*.tar.gz user@server:/path-to-images-directory

# 4. Transfer required folders and scripts to server
scp -r ../models user@server:/path-to-deployment-directory/
scp -r ../keycloak user@server:/path-to-deployment-directory/
scp -r ../src/event-processor/templates user@server:/path-to-deployment-directory/
scp get-token.sh user@server:/path-to-deployment-directory/

# 5. On server: Load images
ssh user@server
cd /path-to-images-directory
docker load -i be-master-service.tar.gz
docker load -i be-celery-worker.tar.gz
docker load -i be-event-processor.tar.gz
docker load -i be-classification-service.tar.gz
docker load -i be-tracking-service.tar.gz
docker load -i be-pipeline-service.tar.gz

# 6. On server: Create database schemas
cd /path-to-deployment-directory
docker compose up -d postgres

docker compose exec -i postgres psql -U security_user -d security_system <<EOF
CREATE SCHEMA IF NOT EXISTS master_service;
CREATE SCHEMA IF NOT EXISTS event_processor;
CREATE SCHEMA IF NOT EXISTS keycloak;
EOF

# 7. Start services on server
docker compose up -d
```

### 4. Verify Services Are Running

```bash
# Check all services status
docker compose ps

# View logs
docker compose logs -f
```

### 5. Insert and Update Camera Information

Add camera configurations to the database:

```bash
# Insert a new camera
docker compose exec -i postgres psql -U security_user -d security_system <<EOF
INSERT INTO master_service.camera (camera_id, email, camera_url, expected_fps, record_fps, is_video, buffersize)
VALUES ('CAM-1', 'user@example.com', 'rtsp://camera-url:554/stream', 24, 24, false, 0);
EOF
```

**Camera fields:**
- `camera_id`: Unique identifier for the camera
- `email`: Email address for notifications
- `camera_url`: RTSP stream URL or video file path
- `expected_fps`: Expected FPS for processing
- `record_fps`: FPS for video recording
- `is_video`: `true` if camera_url is a video file, `false` for stream
- `buffersize`: Buffer size for video capture

**Update an existing camera:**
```bash
docker compose exec -i postgres psql -U security_user -d security_system <<EOF
UPDATE master_service.camera
SET email = 'newemail@example.com',
    camera_url = 'rtsp://new-url:554/stream',
    updated_at = now()
WHERE camera_id = 'CAM-1';
EOF
```

### 6. Run Camera Stream Using Swagger

Start camera stream processing using the Swagger UI:

**Step 1: Get Access Token**

```bash
# Get authentication token using the provided script
./get-token.sh
```

Or manually:
```bash
docker compose exec master-service python -c "
import requests, sys, json
try:
    url = 'http://keycloak:8080/realms/security-realm/protocol/openid-connect/token'
    data = {
        'client_id': 'master-service',
        'client_secret': 'master-service-secret',
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    token = response.json()['access_token']
    print(token)
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
"
```

**Step 2: Access Swagger UI**

1. Open your browser and navigate to: **http://localhost:8000/docs**
2. Click the **"Authorize"** button at the top right
3. In the "Value" field, enter: `Bearer <your-token>` (replace `<your-token>` with the token from Step 1)
4. Click **"Authorize"** and then **"Close"**

**Step 3: Start Camera Stream**

1. Find the endpoint: **POST** `/api/v1/camera/{camera_id}/start-stream`
2. Click **"Try it out"**
3. Enter the `camera_id` (e.g., `CAM-1`) in the path parameter
4. Click **"Execute"**
5. The response will show the task status and `task_id`

**Check Active Streams**

To see all active camera streams: **GET** `/api/v1/tasks/active`

### 7. Access Services

- **Master Service API**: http://localhost:8000
- **Keycloak Admin**: http://localhost:8088
- **MinIO Console**: http://localhost:9001
- **Kafka UI**: http://localhost:8080

## Common Commands

```bash
# Stop all services
docker compose down

# Restart a specific service
docker compose restart master-service

# View logs for a service
docker compose logs -f celery-worker

# Rebuild and restart
docker compose build --no-cache && docker compose up -d
```

## Troubleshooting

**Services won't start?**
```bash
docker compose logs | grep -i error
```

**Database connection issues?**
```bash
docker compose ps postgres
docker compose logs postgres
```


