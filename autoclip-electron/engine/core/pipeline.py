import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Suppress tqdm progress bars globally - prevents stdout pollution
# Our custom IPC_EVENT system handles all progress reporting
os.environ['TQDM_DISABLE'] = '1'

from .downloader import VideoDownloader
from .audio import AudioExtractor
from .transcription import Transcriber
from .highlight import HighlightDetector
from .face_detection import FaceDetector
from .subtitle import SubtitleGenerator
from .clipper import VideoClipper
from .progress import ProgressEmitter
from .logger import StructuredLogger


class AutoClipPipeline:
    """Main pipeline orchestrator for AutoClip"""

    def __init__(self, config_path: str = "config/settings.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.logger = StructuredLogger(self.config.get('logging', {}).get('level', 'INFO')).get_logger()

        # Initialize components
        self.downloader = VideoDownloader(self.config.get('temp_dir', './temp'))
        self.audio_extractor = AudioExtractor(self.config.get('temp_dir', './temp'))
        self.transcriber = Transcriber(self.config.get('whisper_model', 'small'))
        self.highlight_detector = HighlightDetector(self.config.get('highlight', {}))
        self.face_detector = FaceDetector(self.config.get('face_detection', {}))
        self.subtitle_generator = SubtitleGenerator(self.config.get('subtitle', {}))
        self.clipper = VideoClipper(self.config.get('output_dir', './output'), self.config.get('ffmpeg', {}))

    def process(self, input_source: str, output_dir: Optional[str] = None,
               max_clips: Optional[int] = None, clip_duration: Optional[int] = None,
               project_name: Optional[str] = None, enable_crop: Optional[bool] = None) -> Dict:
        """Main processing pipeline"""

        # Override config with CLI args
        if output_dir:
            self.config['output_dir'] = output_dir
            self.clipper.output_dir = Path(output_dir)
            self.clipper.output_dir.mkdir(exist_ok=True)

        if max_clips:
            self.config['max_clips'] = max_clips

        if clip_duration:
            self.config['clip_duration'] = clip_duration

        if project_name:
            self.config['project_name'] = project_name
            self.clipper.project_name = project_name

        if enable_crop is not None:
            self.config['enable_crop'] = enable_crop
            self.clipper.enable_crop = enable_crop

        try:
            self.logger.info(f"Starting AutoClip pipeline for: {input_source}")

            # Emit started state
            ProgressEmitter.emit_state("started")

            # Step 1: Resolve input
            video_path = self._resolve_input(input_source)

            # Step 2: Extract audio
            ProgressEmitter.emit_progress("extracting_audio", 10)
            audio_path = self.audio_extractor.extract_audio(video_path)
            ProgressEmitter.emit_progress("extracting_audio", 20)

            # Step 3: Transcribe audio
            ProgressEmitter.emit_progress("transcribing", 20)
            transcription = self.transcriber.transcribe(audio_path)
            segments = self.transcriber.get_segments(transcription)
            ProgressEmitter.emit_progress("transcribing", 40)

            # Step 3.5: Generate subtitles (after transcription)
            ProgressEmitter.emit_progress("generating_subtitles", 40)
            self.subtitle_generator.generate_subtitle_file(segments, audio_path)
            ProgressEmitter.emit_progress("generating_subtitles", 50)

            # Step 4: Detect highlights
            ProgressEmitter.emit_progress("detecting_highlights", 50)
            highlights = self.highlight_detector.detect_highlights(audio_path, segments)
            ProgressEmitter.emit_progress("detecting_highlights", 70)

            # Step 5: Face detection analysis
            ProgressEmitter.emit_progress("detecting_faces", 70)
            highlights_with_faces = self.face_detector.analyze_highlights(video_path, highlights)
            ProgressEmitter.emit_progress("detecting_faces", 80)

            # Step 6: Filter highlights with faces (optional enhancement)
            face_config = self.config.get('face_detection', {})
            if face_config.get('enabled', True):
                # Keep highlights with faces for better quality
                final_highlights = [h for h in highlights_with_faces if h.get('face_present', True)]
                if len(final_highlights) == 0:
                    # Fallback to original if no faces found
                    final_highlights = highlights
                    self.logger.warning("No highlights with faces found, using all highlights")
            else:
                final_highlights = highlights

            # Step 7: Create clips
            ProgressEmitter.emit_progress("creating_clips", 80)
            clips = self.clipper.create_clips(video_path, final_highlights)
            ProgressEmitter.emit_progress("creating_clips", 100)

            # Calculate total duration
            total_duration = sum(highlight['end'] - highlight['start'] for highlight in highlights)

            # Emit complete
            ProgressEmitter.emit_complete(len(clips))

            # Emit completed state
            ProgressEmitter.emit_state("completed")

            result = {
                'success': True,
                'total_clips': len(clips),
                'total_duration': total_duration,
                'output_dir': str(self.clipper.output_dir),
                'clips': clips
            }

            self.logger.info(f"Pipeline completed: {len(clips)} clips created")
            return result

        except Exception as e:
            error_msg = f"Pipeline failed: {str(e)}"
            ProgressEmitter.emit_error(error_msg)
            self.logger.error(error_msg)
            raise

    def _resolve_input(self, input_source: str) -> str:
        """Resolve input: download if URL, validate if file"""
        ProgressEmitter.emit_progress("resolving_input", 0)

        if input_source.startswith('http'):
            # Assume YouTube URL
            if not self.downloader.is_youtube_url(input_source):
                ProgressEmitter.emit_error(f"Invalid YouTube URL: {input_source}")
                raise ValueError(f"Invalid YouTube URL: {input_source}")
            # Download from YouTube
            video_path = self.downloader.download(input_source)
        else:
            # Validate local file
            if not self.downloader.validate_local_file(input_source):
                ProgressEmitter.emit_error(f"Invalid video file: {input_source}")
                raise ValueError(f"Invalid video file: {input_source}")
            video_path = input_source

        ProgressEmitter.emit_progress("resolving_input", 100, video_path=video_path)
        return video_path