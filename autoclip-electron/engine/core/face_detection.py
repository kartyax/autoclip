import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions, RunningMode
from mediapipe.tasks.python.components.containers import detections
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from .progress import ProgressEmitter
from .logger import StructuredLogger


class FaceDetector:
    """Face detection using MediaPipe for highlight filtering"""

    def __init__(self, config: Dict):
        self.config = config
        self.logger = StructuredLogger().get_logger()
        self.face_detector = None

        if config.get('enabled', True):
            try:
                # Initialize MediaPipe Face Detection with new API
                options = FaceDetectorOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=None),  # Use default model
                    running_mode=RunningMode.IMAGE,
                    min_detection_confidence=config.get('min_detection_confidence', 0.5)
                )
                self.face_detector = FaceDetector.create_from_options(options)
            except Exception as e:
                self.logger.warning(f"Failed to initialize face detector: {e}")
                self.face_detector = None

    def analyze_highlights(self, video_path: str, highlights: List[Dict]) -> List[Dict]:
        """Analyze highlights for face presence"""
        if not self.config.get('enabled', True) or self.face_detector is None:
            self.logger.info("Face detection disabled or not available, skipping")
            return highlights

        self.logger.info(f"Starting face detection analysis on {len(highlights)} highlights")

        ProgressEmitter.emit_progress("face_detection", 0)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_skip = self.config.get('frame_skip', 10)

        analyzed_highlights = []

        for i, highlight in enumerate(highlights):
            face_present, face_ratio = self._analyze_highlight_frames(
                cap, highlight, fps, frame_skip
            )

            # Add face detection results
            highlight_with_face = highlight.copy()
            highlight_with_face.update({
                'face_present': face_present,
                'face_ratio': face_ratio
            })

            analyzed_highlights.append(highlight_with_face)

            ProgressEmitter.emit_progress("face_detection",
                                         int((i + 1) / len(highlights) * 100))

        cap.release()

        # Filter highlights with faces if enabled
        if self.config.get('enabled', True):
            faces_found = sum(1 for h in analyzed_highlights if h['face_present'])
            self.logger.info(f"Face detected in {faces_found}/{len(highlights)} highlights")

        return analyzed_highlights

    def _analyze_highlight_frames(self, cap: cv2.VideoCapture,
                                highlight: Dict, fps: float,
                                frame_skip: int) -> Tuple[bool, float]:
        """Analyze frames in a highlight segment"""
        start_time = highlight['start']
        end_time = highlight['end']

        # Convert to frame numbers
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps)

        faces_detected = 0
        total_frames_analyzed = 0

        # Sample frames throughout the highlight
        for frame_num in range(start_frame, end_frame, frame_skip):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()

            if not ret:
                continue

            # Convert BGR to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Detect faces
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            results = self.face_detector.detect(mp_image)

            if results:
                # Count faces (but we only care if any face is present)
                faces_detected += 1

            total_frames_analyzed += 1

            # Early exit if we find faces in multiple frames
            if faces_detected >= 3:  # Found faces in at least 3 frames
                break

        # Calculate face presence ratio
        face_ratio = faces_detected / max(total_frames_analyzed, 1)

        # Consider face present if detected in >30% of analyzed frames
        face_present = face_ratio > 0.3

        return face_present, face_ratio

    def get_face_bounding_box(self, frame, face_detection_result) -> Optional[Tuple[int, int, int, int]]:
        """Extract face bounding box coordinates"""
        if not face_detection_result:
            return None

        # Get the first (most prominent) face
        detection = face_detection_result[0]
        bbox = detection.bounding_box

        h, w, _ = frame.shape
        x = int(bbox.origin_x)
        y = int(bbox.origin_y)
        width = int(bbox.width)
        height = int(bbox.height)

        return (x, y, width, height)