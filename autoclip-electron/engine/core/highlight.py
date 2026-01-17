import librosa
import numpy as np
from typing import List, Dict, Tuple

from .progress import ProgressEmitter
from .logger import StructuredLogger


class HighlightDetector:
    """Detect highlight moments using rule-based approach"""

    def __init__(self, config: Dict):
        self.config = config
        self.logger = StructuredLogger().get_logger()

    def detect_highlights(self, audio_path: str, transcription_segments: List[Dict]) -> List[Dict]:
        """Detect highlight moments from audio and transcription"""
        self.logger.info("Starting highlight detection")

        ProgressEmitter.emit_progress("detecting_highlights", 0)

        # Load audio for analysis
        y, sr = librosa.load(audio_path, sr=None)

        highlights = []

        # 1. Energy-based detection
        energy_highlights = self._detect_energy_peaks(y, sr)
        highlights.extend(energy_highlights)

        # 2. Keyword detection
        keyword_highlights = self._detect_keywords(transcription_segments)
        highlights.extend(keyword_highlights)

        # 3. Silence gap detection
        silence_highlights = self._detect_silence_gaps(y, sr)
        highlights.extend(silence_highlights)

        # Remove duplicates and sort
        highlights = self._merge_highlights(highlights)

        ProgressEmitter.emit_progress("detecting_highlights", 100,
                                     total_highlights=len(highlights))

        self.logger.info(f"Detected {len(highlights)} highlight moments")
        return highlights[:self.config.get('max_clips', 5)]

    def _detect_energy_peaks(self, y: np.ndarray, sr: int) -> List[Dict]:
        """Detect energy peaks in audio"""
        # RMS energy
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]

        # Normalize
        rms_norm = rms / np.max(rms)

        # Find peaks above threshold
        peaks = []
        threshold = self.config.get('energy_threshold', 0.8)

        for i, energy in enumerate(rms_norm):
            if energy > threshold:
                time = librosa.frames_to_time(i, sr=sr, hop_length=512)
                peaks.append({
                    'start': max(0, time - 5),  # 5 seconds before
                    'end': time + 5,  # 5 seconds after
                    'type': 'energy',
                    'confidence': float(energy)
                })

        return peaks

    def _detect_keywords(self, segments: List[Dict]) -> List[Dict]:
        """Detect keyword-based highlights"""
        keywords = self.config.get('keywords', ['wow', 'amazing'])
        highlights = []

        for segment in segments:
            text = segment['text'].lower()
            for keyword in keywords:
                if keyword in text:
                    highlights.append({
                        'start': segment['start'],
                        'end': segment['end'],
                        'type': 'keyword',
                        'keyword': keyword,
                        'confidence': segment.get('confidence', 0.8)
                    })
                    break

        return highlights

    def _detect_silence_gaps(self, y: np.ndarray, sr: int) -> List[Dict]:
        """Detect silence gaps (potential for punchlines)"""
        # Detect non-silent intervals
        intervals = librosa.effects.split(y,
                                        top_db=self.config.get('silence_threshold', 20),
                                        frame_length=2048,
                                        hop_length=512)

        highlights = []
        min_duration = self.config.get('silence_min_duration', 2.0)

        # Look for gaps between speech
        for i in range(len(intervals) - 1):
            end_time = librosa.samples_to_time(intervals[i][1], sr=sr)
            start_time = librosa.samples_to_time(intervals[i + 1][0], sr=sr)
            gap = start_time - end_time

            if gap >= min_duration:
                # Highlight the moment after silence
                highlights.append({
                    'start': end_time,
                    'end': min(start_time, end_time + self.config.get('clip_duration', 30)),
                    'type': 'silence_gap',
                    'gap_duration': gap,
                    'confidence': 0.7
                })

        return highlights

    def _merge_highlights(self, highlights: List[Dict]) -> List[Dict]:
        """Merge overlapping highlights and remove duplicates"""
        if not highlights:
            return []

        # Sort by start time
        highlights.sort(key=lambda x: x['start'])

        merged = [highlights[0]]

        for current in highlights[1:]:
            last = merged[-1]

            # Check overlap
            if current['start'] <= last['end']:
                # Merge
                last['end'] = max(last['end'], current['end'])
                last['confidence'] = max(last['confidence'], current['confidence'])
                last['types'] = last.get('types', [last['type']]) + [current['type']]
            else:
                merged.append(current)

        return merged