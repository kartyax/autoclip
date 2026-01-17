import yt_dlp
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, cast

from .progress import ProgressEmitter
from .logger import StructuredLogger


class VideoDownloader:
    """Download videos from YouTube using yt-dlp"""

    def __init__(self, output_dir: str = "./temp"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.logger = StructuredLogger().get_logger()

    def is_youtube_url(self, url: str) -> bool:
        """Check if URL is a YouTube URL"""
        try:
            parsed = urlparse(url)
            return 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc
        except:
            return False

    def download(self, url: str) -> str:
        """Download video from YouTube URL"""
        if not self.is_youtube_url(url):
            raise ValueError("Invalid YouTube URL")

        self.logger.info(f"Starting download from: {url}")

        # yt-dlp options with fallback formats for better compatibility
        ydl_opts: Dict[str, Any] = {
            'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            'format': 'best[height<=720]/best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',  # Fallback formats
            'merge_output_format': 'mp4',  # Force MP4 output
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,  # Handle SSL issues
            'retries': 3,  # Retry failed downloads
            'fragment_retries': 3,  # Retry fragmented downloads
            'skip_unavailable_fragments': True,  # Skip unavailable parts
            'http_chunk_size': 1048576,  # 1MB chunks for stability
        }

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                # Get info first
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'video')
                duration = info.get('duration', 0)

                ProgressEmitter.emit_progress("downloading", 0,
                                             title=title, duration=duration)

                # Download
                ydl.download([url])

                # Find and validate downloaded file
                for file in self.output_dir.iterdir():
                    if file.is_file() and file.suffix in ['.mp4', '.webm', '.mkv']:
                        # Validate file
                        if self._validate_downloaded_file(str(file)):
                            self.logger.info(f"Downloaded and validated: {file.name}")
                            ProgressEmitter.emit_progress("downloading", 100,
                                                         file=str(file))
                            return str(file)
                        else:
                            # Delete invalid file
                            file.unlink()
                            self.logger.warning(f"Invalid downloaded file deleted: {file.name}")

                raise FileNotFoundError("No valid downloaded file found")

        except Exception as e:
            ProgressEmitter.emit_error(f"Download failed: {str(e)}")
            raise

    def _validate_downloaded_file(self, file_path: str) -> bool:
        """Validate downloaded file: check size and readability"""
        try:
            # Check file size (>0)
            if os.path.getsize(file_path) == 0:
                return False

            # Try to probe with ffmpeg
            import ffmpeg  # type: ignore
            probe = ffmpeg.probe(file_path, quiet=True)

            # Check if it has video stream
            video_streams = [s for s in probe['streams'] if s['codec_type'] == 'video']
            if not video_streams:
                return False

            # Check duration (>0)
            duration = float(probe['format']['duration'])
            if duration <= 0:
                return False

            return True

        except Exception as e:
            self.logger.warning(f"File validation failed for {file_path}: {str(e)}")
            return False

    def validate_local_file(self, file_path: str) -> bool:
        """Validate local video file"""
        if not os.path.exists(file_path):
            return False

        ext = Path(file_path).suffix.lower()
        valid_exts = ['.mp4', '.mov', '.mkv', '.avi', '.webm']

        return ext in valid_exts