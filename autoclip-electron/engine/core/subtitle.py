import re
import os
import ffmpeg
from typing import List, Dict, Optional
from pathlib import Path
from .progress import ProgressEmitter
from .logger import StructuredLogger


class SubtitleGenerator:
    """Generate TikTok-style subtitles and burn them into videos"""

    def __init__(self, config: Dict):
        self.config = config
        self.logger = StructuredLogger().get_logger()

        # Subtitle configuration
        self.style = config.get('style', 'tiktok')
        self.position = config.get('position', 'center')
        self.color = config.get('color', 'white')
        self.uppercase = config.get('uppercase', True)
        self.max_words_per_line = config.get('max_words_per_line', 6)

        # Highlight keywords for emphasis
        self.highlight_keywords = config.get('highlight_keywords', [
            'wow', 'gokil', 'parah', 'gila', 'amazing', 'incredible',
            'awesome', 'brilliant', 'sangat', 'benar-benar'
        ])

    def generate_subtitles_for_clip(self, transcription_segments: List[Dict],
                                  clip_start: float, clip_end: float) -> List[Dict]:
        """Generate subtitle entries for a specific clip time range"""
        # Filter segments within clip time range
        clip_segments = [
            seg for seg in transcription_segments
            if seg['start'] >= clip_start - 0.5 and seg['end'] <= clip_end + 0.5
        ]

        if not clip_segments:
            return []

        subtitles = []
        current_time = clip_start

        for segment in clip_segments:
            # Split segment into subtitle phrases
            phrases = self._split_into_phrases(segment)

            for phrase_text, phrase_start, phrase_end in phrases:
                # Adjust timing to clip range
                adjusted_start = max(phrase_start, clip_start)
                adjusted_end = min(phrase_end, clip_end)

                if adjusted_end - adjusted_start < 0.5:  # Skip too short
                    continue

                # Create subtitle entry
                subtitle = {
                    'text': phrase_text,
                    'start': adjusted_start,
                    'end': adjusted_end,
                    'is_highlight': self._is_highlight_text(phrase_text)
                }

                subtitles.append(subtitle)

        # Merge overlapping or too close subtitles
        subtitles = self._merge_subtitles(subtitles)

        return subtitles

    def _split_into_phrases(self, segment: Dict) -> List[tuple]:
        """Split transcription segment into subtitle phrases"""
        text = segment['text'].strip()
        segment_start = segment['start']
        segment_end = segment['end']

        # Split by sentence endings and pause points
        sentences = re.split(r'([.!?]+)', text)

        phrases = []
        current_time = segment_start

        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i].strip()
            punctuation = sentences[i + 1] if i + 1 < len(sentences) else ''

            if not sentence:
                continue

            # Split long sentences into shorter phrases
            words = sentence.split()
            if len(words) > self.max_words_per_line * 2:
                # Split into multiple lines
                chunks = [words[i:i + self.max_words_per_line]
                         for i in range(0, len(words), self.max_words_per_line)]
                for chunk in chunks:
                    if chunk:
                        phrase_text = ' '.join(chunk)
                        # Estimate timing for each chunk
                        duration_per_word = (segment_end - segment_start) / len(words)
                        phrase_duration = len(chunk) * duration_per_word
                        phrase_end = current_time + phrase_duration

                        phrases.append((phrase_text, current_time, phrase_end))
                        current_time = phrase_end
            else:
                # Single phrase
                phrase_duration = min(segment_end - current_time, 2.5)  # Max 2.5s
                phrase_end = current_time + phrase_duration
                phrases.append((sentence + punctuation, current_time, phrase_end))
                current_time = phrase_end

        return phrases

    def _is_highlight_text(self, text: str) -> bool:
        """Check if text contains highlight keywords"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.highlight_keywords)

    def _merge_subtitles(self, subtitles: List[Dict]) -> List[Dict]:
        """Merge overlapping or very close subtitles"""
        if not subtitles:
            return []

        merged = [subtitles[0]]

        for current in subtitles[1:]:
            last = merged[-1]

            # If they overlap or are very close (< 0.3s gap)
            if current['start'] - last['end'] < 0.3:
                # Merge them
                last['end'] = max(last['end'], current['end'])
                last['text'] += ' ' + current['text']
                last['is_highlight'] = last['is_highlight'] or current['is_highlight']
            else:
                merged.append(current)

        return merged

    def generate_ffmpeg_subtitle_filter(self, subtitles: List[Dict],
                                       video_width: int, video_height: int) -> str:
        """Generate FFmpeg drawtext filter for subtitles"""
        if not subtitles:
            return ""

        filter_parts = []

        # Base font settings
        base_font_size = int(video_height * 0.05)  # 5% of video height
        font_name = "DejaVuSans-Bold"  # Cross-platform sans-serif

        # Determine font file path based on platform
        if os.name == 'nt':  # Windows
            fontfile = 'C:/Windows/Fonts/arial.ttf'
        elif hasattr(os, 'uname') and os.uname().sysname == 'Darwin':  # macOS
            fontfile = '/System/Library/Fonts/Arial.ttf'
        else:  # Linux and others
            fontfile = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

        for i, subtitle in enumerate(subtitles):
            text = subtitle['text']
            if self.uppercase:
                text = text.upper()

            start_time = subtitle['start']
            end_time = subtitle['end']
            is_highlight = subtitle.get('is_highlight', False)

            # Adjust font size and color for highlights
            if is_highlight:
                font_size = int(base_font_size * 1.5)
                font_color = "yellow" if self.color == "white" else "cyan"
                # Add fire emoji for extra emphasis
                text += " 🔥"
            else:
                font_size = base_font_size
                font_color = self.color

            # Position calculation
            if self.position == 'center':
                x_pos = "(w-text_w)/2"
                y_pos = f"(h-text_h)-{int(video_height * 0.15)}"  # 15% from bottom
            else:  # bottom
                x_pos = "(w-text_w)/2"
                y_pos = f"(h-text_h)-{int(video_height * 0.1)}"   # 10% from bottom

            # Escape special characters for FFmpeg
            text_escaped = text.replace("'", "\\'").replace(":", "\\:")

            # Create drawtext filter
            fontfile_part = f"fontfile={fontfile}:" if fontfile else ""
            drawtext = (
                f"drawtext={fontfile_part}"
                f"font={font_name}:"
                f"text='{text_escaped}':"
                f"fontsize={font_size}:"
                f"fontcolor={font_color}:"
                f"x={x_pos}:y={y_pos}:"
                f"shadowx=2:shadowy=2:shadowcolor=black@0.5:"  # Shadow for contrast
                f"enable=between(t\\,{start_time:.2f}\\,{end_time:.2f})"
            )

            filter_parts.append(drawtext)

        # Combine all drawtext filters
        return ','.join(filter_parts) if filter_parts else ""

    def generate_subtitle_file(self, segments: List[Dict], audio_path: str) -> str:
        """Generate .srt subtitle file from transcription segments"""
        srt_path = Path(audio_path).with_suffix('.srt')

        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                start = self._format_timestamp(segment['start'])
                end = self._format_timestamp(segment['end'])
                text = segment['text'].strip()
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

        ProgressEmitter.emit_subtitle("global", str(srt_path))
        return str(srt_path)

    def generate_clip_subtitle_file(self, subtitles: List[Dict], output_video: str) -> str:
        """Generate SRT file for clip subtitles"""
        srt_path = Path(output_video).with_suffix('.srt')

        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles, 1):
                start = self._format_timestamp(sub['start'])
                end = self._format_timestamp(sub['end'])
                text = sub['text']
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

        return str(srt_path)

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds to SRT timestamp format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    def burn_subtitles_into_clip(self, input_video: str, output_video: str,
                               subtitles: List[Dict]) -> bool:
        """Burn subtitles directly into video clip using SRT file and TikTok-style force_style"""
        try:
            if not subtitles:
                # No subtitles, just copy video
                stream = ffmpeg.input(input_video)
                stream = ffmpeg.output(stream, output_video, vcodec='libx264', acodec='aac')
                ffmpeg.run(stream, overwrite_output=True, quiet=True)
                return True

            # Generate SRT file for clip
            srt_path = self.generate_clip_subtitle_file(subtitles, output_video)

            ProgressEmitter.emit_progress("subtitles", 0, style=self.style)

            stream = ffmpeg.input(input_video)

            # Apply subtitles filter with TikTok-style force_style
            vf = f"subtitles={srt_path}:force_style='Fontsize=24,Alignment=2,Outline=2'"

            stream = ffmpeg.output(stream, output_video, vf=vf, vcodec='libx264', acodec='aac')

            ffmpeg.run(stream, overwrite_output=True, quiet=True)

            ProgressEmitter.emit_progress("subtitles", 100, style=self.style)

            self.logger.info(f"Burned {len(subtitles)} subtitles into {Path(output_video).name}")
            return True

        except ffmpeg.Error as e:
            error_msg = f"Subtitle burning failed: {e.stderr.decode()}" if e.stderr else str(e)
            ProgressEmitter.emit_error(error_msg)
            self.logger.error(error_msg)
            return False