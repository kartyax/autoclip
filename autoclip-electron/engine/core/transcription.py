import os
os.environ['TQDM_DISABLE'] = '1'  # Must be set before importing faster_whisper

from faster_whisper import WhisperModel
from pathlib import Path
from typing import List, Dict, Any

from .progress import ProgressEmitter
from .logger import StructuredLogger


class Transcriber:
    """Transcribe audio using Faster-Whisper (4-5x faster than vanilla Whisper)"""

    def __init__(self, model_size: str = "small"):
        self.model_size = model_size
        self.model = None
        self.logger = StructuredLogger().get_logger()

    def load_model(self):
        """Load Faster-Whisper model"""
        if self.model is None:
            self.logger.info(f"Loading Faster-Whisper model: {self.model_size}")
            try:
                # Use CPU with int8 for speed, or "float16" for better accuracy
                # device="cuda" if GPU available
                self.model = WhisperModel(
                    self.model_size, 
                    device="cpu", 
                    compute_type="int8"
                )
                self.logger.info("Faster-Whisper model loaded successfully")
            except Exception as e:
                ProgressEmitter.emit_error(f"Failed to load Faster-Whisper model: {str(e)}")
                raise

    def transcribe(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe audio file"""
        if self.model is None:
            self.load_model()

        audio_file = Path(audio_path)
        self.logger.info(f"Starting transcription: {audio_file.name}")

        ProgressEmitter.emit_progress("transcribing", 0)

        try:
            # Faster-Whisper API returns generator
            segments_generator, info = self.model.transcribe(
                str(audio_file),
                language=None,  # Auto-detect
                task="transcribe",
                beam_size=5,
                vad_filter=True  # Voice Activity Detection for better accuracy
            )

            # Convert generator to list (needed for compatibility)
            segments_list = list(segments_generator)
            
            # Detect language from info
            detected_language = info.language if hasattr(info, 'language') else 'unknown'
            self.logger.info(f"Detected language: {detected_language}")

            # Build result compatible with old Whisper format
            result = {
                'language': detected_language,
                'segments': []
            }

            for segment in segments_list:
                result['segments'].append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text,
                    'confidence': segment.avg_logprob if hasattr(segment, 'avg_logprob') else 0.0
                })

            ProgressEmitter.emit_progress("transcribing", 100,
                                         segments=len(result['segments']),
                                         language=detected_language)

            self.logger.info(f"Transcription completed: {len(result['segments'])} segments")
            return result

        except Exception as e:
            ProgressEmitter.emit_error(f"Transcription failed: {str(e)}")
            raise

    def get_segments(self, transcription_result: Dict) -> List[Dict]:
        """Extract segments with timestamps"""
        segments = []
        for segment in transcription_result.get('segments', []):
            segments.append({
                'start': segment['start'],
                'end': segment['end'],
                'text': segment['text'].strip(),
                'confidence': segment.get('confidence', 0.0)
            })
        return segments