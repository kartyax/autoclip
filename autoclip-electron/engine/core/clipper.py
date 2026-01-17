import ffmpeg
from pathlib import Path
import os
from typing import List, Dict, Optional

from .progress import ProgressEmitter
from .logger import StructuredLogger


class VideoClipper:
    """Clip video segments using FFmpeg"""

    def __init__(self, output_dir: str = "./output", config: Optional[Dict] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.config = config or {}
        self.logger = StructuredLogger().get_logger()
        self.project_name = "Untitled"  # Default project name
        self.enable_crop = self.config.get('enable_crop', True)  # Enable crop by default

        # Crop settings
        self.crop_config = self.config.get('crop', {})
        self.aspect_ratio = self.crop_config.get('aspect_ratio', '16:9')
        self.target_width = self.crop_config.get('target_width', 1920)
        self.target_height = self.crop_config.get('target_height', 1080)

        # Subtitle settings
        from .subtitle import SubtitleGenerator
        self.subtitle_generator = SubtitleGenerator(self.config.get('subtitle', {}))

    def create_clips(self, video_path: str, highlights: List[Dict],
                    transcription_segments: Optional[List[Dict]] = None) -> List[str]:
        """Create video clips from highlights with optional subtitles"""
        video_file = Path(video_path)
        clips = []

        total_clips = len(highlights)
        self.logger.info(f"Creating {total_clips} video clips")

        subtitle_enabled = self.config.get('subtitle', {}).get('enabled', True)

        for i, highlight in enumerate(highlights):
            clip_path = self._create_clip_with_subtitle(video_file, highlight, i + 1,
                                                       transcription_segments if subtitle_enabled else None)
            if clip_path:
                clips.append(clip_path)
                # Emit clip creation event
                duration = int(highlight['end'] - highlight['start'])
                ProgressEmitter.emit_clip(clip_path, duration)

            ProgressEmitter.emit_progress("creating_clips",
                                         int((i + 1) / total_clips * 100),
                                         current_clip=i + 1,
                                         total_clips=total_clips)

        self.logger.info(f"Created {len(clips)} clips successfully")
        return clips

    def _create_clip_with_subtitle(self, video_path: Path, highlight: Dict, clip_number: int,
                                  transcription_segments: Optional[List[Dict]] = None) -> Optional[str]:
        """Create single video clip with 16:9 cropping and optional subtitles"""
        start_time = highlight['start']
        duration = min(highlight['end'] - highlight['start'],
                      self.config.get('clip_duration', 30))

        # Clean project name for filename (remove invalid characters)
        clean_name = "".join(c for c in self.project_name if c.isalnum() or c in (' ', '-', '_')).strip()
        clean_name = clean_name.replace(' ', '_')  # Replace spaces with underscores
        
        # New format: ProjectName_001.mp4 (no timestamp)
        clip_filename = f"{clean_name}_{clip_number:03d}.mp4"
        clip_path = self.output_dir / clip_filename

        try:
            ProgressEmitter.emit_progress("cropping", 0, aspect=self.aspect_ratio)

            # Create temporary clip path for initial processing
            temp_clip_path = self.output_dir / f"temp_{clip_filename}"

            # Check if crop is enabled
            self.logger.info(f"[DEBUG] enable_crop value: {self.enable_crop}")  # Debug
            
            if self.enable_crop:
                # Try cropped clip first, fallback to simple clip if fails
                self.logger.info(f"Crop ENABLED for clip {clip_number}, creating cropped clip")
                crop_success = self._try_create_cropped_clip(video_path, start_time, duration, temp_clip_path)
                
                if not crop_success:
                    # Fallback: create simple clip without crop
                    self.logger.warning(f"Crop failed for clip {clip_number}, using fallback (no crop)")
                    crop_success = self._create_simple_clip(video_path, start_time, duration, temp_clip_path)
            else:
                # Crop disabled, create simple clip directly (faster)
                self.logger.info(f"Crop DISABLED for clip {clip_number}, creating simple clip")
                crop_success = self._create_simple_clip(video_path, start_time, duration, temp_clip_path)
            
            if not crop_success:
                ProgressEmitter.emit_error(f"Failed to create clip {clip_number}")
                return None

            ProgressEmitter.emit_progress("cropping", 100, aspect=self.aspect_ratio)
            self.logger.info(f"Created clip: {clip_filename}")

            # Handle subtitles if transcription is provided
            if transcription_segments:
                clip_start = start_time
                clip_end = start_time + duration

                # Generate subtitles for this clip
                subtitles = self.subtitle_generator.generate_subtitles_for_clip(
                    transcription_segments, clip_start, clip_end
                )

                if subtitles:
                    # Burn subtitles into the clip
                    success = self.subtitle_generator.burn_subtitles_into_clip(
                        str(temp_clip_path), str(clip_path), subtitles
                    )
                    if success:
                        self.logger.info(f"Burned {len(subtitles)} subtitles into {clip_filename}")
                    else:
                        # If burning failed, copy temp file to final
                        temp_clip_path.replace(clip_path)
                        self.logger.warning(f"Failed to burn subtitles, using clip without subtitles")
                else:
                    # No subtitles generated, just rename temp file
                    temp_clip_path.replace(clip_path)
            else:
                # No transcription, just rename temp file
                temp_clip_path.replace(clip_path)

            # Clean up temp file if it still exists
            if temp_clip_path.exists():
                temp_clip_path.unlink()

            return str(clip_path)

        except Exception as e:
            error_msg = f"Clip creation error: {str(e)}"
            ProgressEmitter.emit_error(f"Failed to create clip {clip_number}: {error_msg}")
            self.logger.error(error_msg)
            return None

    def _try_create_cropped_clip(self, video_path: Path, start_time: float, 
                                  duration: float, output_path: Path) -> bool:
        """Try to create a cropped clip. Returns True on success, False on failure."""
        try:
            # Input stream
            stream = ffmpeg.input(str(video_path), ss=start_time, t=duration)

            # Apply crop filter for 16:9
            crop_filter = self._get_crop_filter(str(video_path), stream)

            # Chain scale and pad filters in the complex filtergraph (not as simple vf)
            # This avoids the "simple and complex filtering cannot be used together" error
            video_filter = crop_filter.filter(
                'scale', 
                self.target_width, 
                self.target_height, 
                force_original_aspect_ratio='decrease'
            ).filter(
                'pad',
                self.target_width,
                self.target_height,
                '(ow-iw)/2',
                '(oh-ih)/2'
            )

            # Output with complete video filter chain
            output_stream = ffmpeg.output(
                video_filter,
                str(output_path),
                vcodec=self.config.get('video_codec', 'libx264'),
                acodec='aac',
                preset=self.config.get('preset', 'fast'),
                crf=self.config.get('crf', 23)
            )

            # Run FFmpeg - no quiet=True so we can see errors
            ffmpeg.run(output_stream, overwrite_output=True)
            return True
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            self.logger.warning(f"Cropped clip creation failed: {error_msg}")
            return False

    def _create_simple_clip(self, video_path: Path, start_time: float,
                            duration: float, output_path: Path) -> bool:
        """Create a simple clip without cropping (fallback method)."""
        try:
            stream = ffmpeg.input(str(video_path), ss=start_time, t=duration)
            
            output_stream = ffmpeg.output(
                stream,
                str(output_path),
                vcodec=self.config.get('video_codec', 'libx264'),
                acodec='aac',
                preset=self.config.get('preset', 'fast'),
                crf=self.config.get('crf', 23)
            )

            # Run FFmpeg - no quiet=True so we can see errors
            ffmpeg.run(output_stream, overwrite_output=True)
            self.logger.info(f"Created fallback clip (no crop): {output_path.name}")
            return True
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            self.logger.error(f"Fallback clip creation failed: {error_msg}")
            return False

    def _get_crop_filter(self, video_path: str, stream):
        """Get crop filter based on face detection or center crop"""
        # For now, use center crop. Face-based cropping would require face detection integration
        # This is a simplified implementation - center crop to 16:9

        # Get video info to calculate crop - use video_path, not stream!
        probe = ffmpeg.probe(video_path)
        video_stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        width = int(video_stream['width'])
        height = int(video_stream['height'])

        # Calculate 16:9 crop dimensions
        target_ratio = 16/9
        current_ratio = width / height

        if current_ratio > target_ratio:
            # Video is wider, crop width
            crop_width = int(height * target_ratio)
            crop_height = height
        else:
            # Video is taller, crop height
            crop_width = width
            crop_height = int(width / target_ratio)

        # Center crop coordinates
        x = (width - crop_width) // 2
        y = (height - crop_height) // 2

        return stream.crop(x, y, crop_width, crop_height)