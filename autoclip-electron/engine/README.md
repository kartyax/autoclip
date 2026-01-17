# AutoClip Engine

Python-based engine for automatic video highlight clipping using AI transcription and rule-based highlight detection.

## Features

- **Input Support**: Local video files (MP4, MOV, MKV, AVI) and YouTube URLs
- **Local AI**: Uses OpenAI Whisper for transcription (100% offline)
- **Face Detection**: MediaPipe-based face presence detection for highlight filtering
- **Smart Highlight Detection**: Rule-based detection using energy peaks, keywords, silence gaps, and face presence
- **Auto Crop**: Automatic 16:9 cropping for Shorts/Reels compatibility
- **Robust Downloading**: Enhanced yt-dlp with fallback formats and validation
- **Progress Monitoring**: Real-time JSON progress output for UI integration
- **Stable Pipeline**: Deterministic processing with comprehensive error handling

## Installation

### 1. Setup Virtual Environment (Recommended)

```bash
cd autoclip-electron/engine

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
# Make sure venv is activated first
pip install -r requirements.txt
```

### 3. Verify Installation

```bash
python -c "import whisper; print('Whisper OK')"
python -c "import yt_dlp; print('yt-dlp OK')"
ffmpeg -version  # Should show FFmpeg version
```

## Usage

### Basic Usage

```bash
python engine.py --input video.mp4 --output ./clips
```

### YouTube Video

```bash
python engine.py --input "https://youtube.com/watch?v=VIDEO_ID" --output ./clips
```

### Advanced Options

```bash
python engine.py \
    --input video.mp4 \
    --output ./my_clips \
    --max-clips 3 \
    --clip-duration 45 \
    --verbose
```

## CLI Arguments

| Argument                | Default                | Description                              |
| ----------------------- | ---------------------- | ---------------------------------------- |
| `--input`, `-i`         | Required               | Video file path or YouTube URL           |
| `--output`, `-o`        | `./output`             | Output directory for clips               |
| `--max-clips`, `-n`     | `5`                    | Maximum number of clips to generate      |
| `--clip-duration`, `-d` | `30`                   | Maximum duration for each clip (seconds) |
| `--verbose`, `-v`       | `False`                | Enable verbose logging                   |
| `--config`              | `config/settings.json` | Path to configuration file               |

## Output

The engine outputs progress and results as JSON to stdout:

```json
{"type":"progress","step":"transcribing","percent":75}
{"type":"log","level":"INFO","message":"Transcription completed"}
{"type":"success","total_clips":5,"total_duration":150.0,"output_dir":"./clips"}
```

## Configuration

Edit `config/settings.json` to customize:

- Whisper model size (`small`, `base`, `medium`, `large`)
- Highlight detection thresholds
- FFmpeg encoding settings
- Logging levels

## Pipeline Steps

1. **Input Resolution**: Download YouTube video (with robust fallback) or validate local file
2. **Audio Extraction**: Extract WAV audio using FFmpeg
3. **Transcription**: Generate timestamps and text using Whisper
4. **Highlight Detection**: Detect moments using energy analysis, keywords, silence gaps
5. **Face Detection**: Analyze highlights for face presence (optional filtering)
6. **Clip Generation**: Create 16:9 cropped video clips using FFmpeg
7. **Report**: Generate success summary with face detection stats

## Requirements

- Python 3.8+
- FFmpeg installed and in PATH
- ~2GB RAM for Whisper small model
- Internet connection for YouTube downloads

## Architecture

```
engine/
├── engine.py              # CLI entry point
├── core/
│   ├── pipeline.py         # Main orchestration
│   ├── downloader.py       # yt-dlp integration
│   ├── audio.py            # FFmpeg audio extraction
│   ├── transcription.py    # Whisper integration
│   ├── highlight.py        # Rule-based detection
│   ├── clipper.py          # FFmpeg video clipping
│   ├── progress.py         # JSON output emitter
│   └── logger.py           # Structured logging
├── config/
│   └── settings.json       # Configuration
└── requirements.txt        # Python dependencies
```

## Integration with Electron UI

The engine is designed to be called from the AutoClip Electron application. Progress output to stdout is consumed by the UI to update progress bars and logs in real-time.

Example UI integration:

```javascript
// In Electron main process
const { spawn } = require("child_process");
const engine = spawn("python", ["engine/engine.py", "--input", inputPath]);

engine.stdout.on("data", (data) => {
  const message = JSON.parse(data.toString());
  // Update UI based on message.type
});
```
