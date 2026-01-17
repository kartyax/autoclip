import ffmpeg
import os
from pathlib import Path

from .progress import ProgressEmitter
from .logger import StructuredLogger


class AudioExtractor:
    """Extract audio from video using FFmpeg"""

    def __init__(self, temp_dir: str = "./temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        self.logger = StructuredLogger().get_logger()

    def extract_audio(self, video_path: str, progress_callback=None) -> str:
        """Extract audio from video file to WAV format"""
        video_file = Path(video_path)
        audio_path = self.temp_dir / f"{video_file.stem}_audio.wav"

        if audio_path.exists():
            self.logger.info("Audio file already exists, skipping extraction")
            return str(audio_path)

        self.logger.info(f"Extracting audio from: {video_file.name}")

        try:
            # FFmpeg command to extract audio
            stream = ffmpeg.input(str(video_path))
            stream = ffmpeg.output(stream, str(audio_path),
                                 acodec='pcm_s16le',
                                 ac=1,  # mono
                                 ar=16000)  # 16kHz for Whisper

            # Run with progress callback
            if progress_callback:
                ffmpeg.run(stream, overwrite_output=True, quiet=True)
                progress_callback(100)
            else:
                ProgressEmitter.emit_progress("extracting_audio", 0)
                ffmpeg.run(stream, overwrite_output=True, quiet=True)
                ProgressEmitter.emit_progress("extracting_audio", 100,
                                            audio_file=str(audio_path))

            self.logger.info(f"Audio extracted: {audio_path.name}")
            return str(audio_path)

        except ffmpeg.Error as e:
            error_msg = f"FFmpeg error: {e.stderr.decode()}" if e.stderr else str(e)
            ProgressEmitter.emit_error(f"Audio extraction failed: {error_msg}")
            raise

    def get_audio_info(self, audio_path: str) -> dict:
        """Get audio file information"""
        try:
            probe = ffmpeg.probe(str(audio_path))
            audio_stream = next(
                (stream for stream in probe['streams']
                 if stream['codec_type'] == 'audio'), None
            )

            if audio_stream:
                return {
                    'duration': float(probe['format']['duration']),
                    'sample_rate': int(audio_stream['sample_rate']),
                    'channels': int(audio_stream['channels']),
                    'codec': audio_stream['codec_name']
                }
            return {}

        except Exception as e:
            self.logger.warning(f"Could not get audio info: {str(e)}")
            return {}