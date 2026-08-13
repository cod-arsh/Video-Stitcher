# Video Stitcher API

A lightweight **FastAPI + FFmpeg** service that automatically builds vertical videos from scene images, voiceovers, and subtitle files stored in Google Drive.

The service accepts a Google Drive folder ID, downloads the assets for each scene, renders individual captioned clips, stitches them together with transitions, uploads the finished video back to Google Drive, and sends the result to a callback URL.

## Features

- FastAPI HTTP API
- Asynchronous video generation using a background thread
- Google Drive OAuth integration
- Downloads scene images, voiceovers, and subtitles from Drive
- Generates **1080 × 1920** vertical video
- Burns `.srt` subtitles directly into each scene
- Adds configurable silence after each voiceover
- Smooth video transitions using FFmpeg `xfade`
- Smooth audio transitions using FFmpeg `acrossfade`
- Uploads/updates `final_video.mp4` in the original Drive folder
- Sends the completed Drive URL and file ID to a callback endpoint

## How It Works

```text
POST /generate-video
        │
        ▼
Validate request
        │
        ▼
Start rendering thread
        │
        ▼
Authenticate with Google Drive
        │
        ▼
Download images + voiceovers + SRT files
        │
        ▼
Render each scene with FFmpeg
        │
        ▼
Burn subtitles into scene clips
        │
        ▼
Stitch clips with video/audio fades
        │
        ▼
Upload final_video.mp4 to Google Drive
        │
        ▼
POST result to callback_url
```

## Project Structure

```text
video stitcher/
├── server.py              # FastAPI application and API endpoints
├── render_pipeline.py     # Video rendering and stitching pipeline
├── drive_utils.py         # Google Drive authentication and file helpers
├── oauth_credentials.json # Google OAuth client credentials — keep private
├── service_account.json   # Legacy/unused by the current Drive implementation
├── token.json             # Generated after OAuth login; should not be committed
└── README.md
```

## Requirements

### System Requirements

- Python 3.9+
- FFmpeg
- FFprobe
- Google account with access to the target Drive folders

Verify FFmpeg is installed:

```bash
ffmpeg -version
ffprobe -version
```

### Python Dependencies

Install the required packages:

```bash
pip install fastapi uvicorn pydantic requests google-api-python-client google-auth google-auth-oauthlib
```

A virtual environment is recommended:

```bash
python -m venv venv
```

Activate it:

**Windows**

```bash
venv\Scripts\activate
```

**macOS / Linux**

```bash
source venv/bin/activate
```

Then install the dependencies.

## Google Drive Setup

The active implementation in `drive_utils.py` uses **Google OAuth 2.0 user authentication**.

1. Create a project in Google Cloud Console.
2. Enable the **Google Drive API**.
3. Configure the OAuth consent screen.
4. Create an OAuth Client ID for a **Desktop app**.
5. Download the credentials JSON.
6. Save it in the project directory as:

```text
oauth_credentials.json
```

On the first request that reaches Google Drive, the application will open a browser window for authorization.

After successful login, a `token.json` file is generated automatically and reused for future requests.

> **Headless/server deployment:** the current OAuth flow uses `run_local_server()`. For a remote server, authenticate once in an environment where the browser OAuth flow can complete and securely provide the resulting token, or replace the authentication implementation with a deployment-appropriate flow.

## Expected Google Drive Folder Structure

The folder passed through `drive_folder_id` must have the following structure:

```text
My Video Folder/
├── images/
│   ├── 1.png
│   ├── 2.png
│   ├── 3.png
│   └── ...
│
├── voices/
│   ├── 1.mp3
│   ├── 2.mp3
│   ├── 3.mp3
│   └── ...
│
├── 1.srt
├── 2.srt
├── 3.srt
└── ...
```

For every scene number, the following files must exist:

```text
images/{scene}.{image_ext}
voices/{scene}.mp3
{scene}.srt
```

For example, a request with:

```json
{
  "num_scenes": 3,
  "image_ext": "png"
}
```

requires:

```text
images/1.png
images/2.png
images/3.png
voices/1.mp3
voices/2.mp3
voices/3.mp3
1.srt
2.srt
3.srt
```

The `.srt` files must be placed in the **root video folder**, not inside a subtitles subfolder.

## Running the API

From the project directory, start the FastAPI server with Uvicorn:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

For development with auto-reload:

```bash
uvicorn server:app --reload
```

The API will be available at:

```text
http://localhost:8000
```

FastAPI interactive documentation:

```text
http://localhost:8000/docs
```

## API Endpoints

### Health Check

```http
GET /
```

Response:

```json
{
  "status": "ok"
}
```

### Generate Video

```http
POST /generate-video
```

Request body:

```json
{
  "drive_folder_id": "GOOGLE_DRIVE_FOLDER_ID",
  "num_scenes": 3,
  "image_ext": "png",
  "callback_url": "https://example.com/video-callback",
  "record_id": "record_123"
}
```

### Request Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `drive_folder_id` | string | Yes | Google Drive folder containing the scene assets |
| `num_scenes` | integer | Yes | Number of scenes to process |
| `image_ext` | string | No | Image extension. Defaults to `png` |
| `callback_url` | string | Yes | URL notified after rendering completes |
| `record_id` | string | Yes | External record/job identifier returned in the callback |

The API immediately returns:

```json
{
  "status": "started"
}
```

Rendering continues in a background thread.

## Callback Response

After rendering and uploading the video, the service sends a `POST` request to `callback_url`.

Example callback payload:

```json
{
  "status": "completed",
  "video_url": "https://drive.google.com/file/d/FILE_ID/view",
  "file_id": "FILE_ID",
  "record_id": "record_123"
}
```

Your callback endpoint should accept JSON POST requests.

## Example Request

Using cURL:

```bash
curl -X POST "http://localhost:8000/generate-video" \
  -H "Content-Type: application/json" \
  -d '{
    "drive_folder_id": "YOUR_DRIVE_FOLDER_ID",
    "num_scenes": 3,
    "image_ext": "png",
    "callback_url": "https://example.com/video-callback",
    "record_id": "record_123"
  }'
```

## Rendering Configuration

The main pipeline is defined in `render_pipeline.py`.

Current defaults:

| Setting | Default |
|---|---:|
| Resolution | `1080x1920` |
| FPS | `25` |
| Silence padding | `0.6 seconds` |
| Transition duration | `0.5 seconds` |
| Transition type | `fade` |
| Video codec | `libx264` |
| Audio codec | `AAC` |
| Audio bitrate | `192k` |
| Pixel format | `yuv420p` |

The pipeline function currently exposes these optional arguments:

```python
run_pipeline(
    drive_folder_id,
    num_scenes,
    callback_url,
    record_id,
    image_ext="png",
    fps=25,
    silence_pad=0.6,
    transition_duration=0.5,
    transition_type="fade"
)
```

## Subtitle Styling

Subtitles are burned into the output using FFmpeg's `subtitles` filter.

The current style uses:

- Liberation Sans Bold
- White text
- Semi-transparent black background
- Bottom-center alignment
- Vertical margin of 60

Make sure the required font and FFmpeg subtitle support are available on the host system.

## Output

The generated file is named:

```text
final_video.mp4
```

It is uploaded to the same Google Drive folder supplied through `drive_folder_id`.

If a file named `final_video.mp4` already exists in that folder, the current upload helper updates the existing Drive file instead of creating another copy.

## Temporary Files

Rendering assets are stored inside a temporary local directory created with Python's `tempfile` module.

After a successful render and upload, the temporary working directory is deleted automatically.

## Important Notes

- Scene numbering starts at `1` and must be sequential.
- Image, voiceover, and subtitle filenames must match the scene number exactly.
- Voiceovers are currently expected to be `.mp3` files.
- Subtitle files are currently expected to be `.srt` files.
- Output is always rendered in vertical `1080x1920` format.
- The current stitching implementation is designed for multiple scenes. Use at least **2 scenes** unless the pipeline is updated to explicitly support a single-scene render.
- The API returns `started` before the render finishes. Completion should be tracked through the callback.
- Rendering errors occurring inside the background thread are currently logged to the server process but are not posted back to the callback endpoint.

## Security

**Do not commit authentication credentials or generated OAuth tokens to Git.**

Add at least the following entries to `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
venv/
.venv/

# Google credentials / tokens
oauth_credentials.json
service_account.json
token.json

# Environment variables
.env

# Generated media
*.mp4
*.mp3
```

> If real Google credentials have already been committed or shared publicly, remove them from the repository history and rotate/revoke the affected credentials in Google Cloud Console.

## Known Limitations

- No job queue or persistent job status storage
- Uses a Python daemon thread rather than a dedicated task queue
- No authentication on the FastAPI endpoint
- No request validation for Drive folder contents before starting the job
- No callback retry mechanism
- No explicit timeout on the callback HTTP request
- No failure callback payload
- OAuth browser login is not ideal for headless production servers
- Single-scene rendering is not explicitly handled by the current stitching stage

For production deployments, consider using a task queue such as Celery/RQ, persistent job states, API authentication, structured logging, callback retries, and deployment-friendly Google authentication.

## License

No license has been specified for this repository yet.
