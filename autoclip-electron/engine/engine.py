#!/usr/bin/env python3
"""
AutoClip Engine - CLI Tool for Automatic Video Highlight Clipping

Usage:
    python engine.py --input <video_file_or_youtube_url> [options]

Examples:
    python engine.py --input video.mp4 --output ./clips
    python engine.py --input "https://youtube.com/watch?v=..." --max-clips 3
"""

import argparse
import sys
import json
from pathlib import Path

from core.pipeline import AutoClipPipeline
from core.progress import ProgressEmitter
from core.logger import StructuredLogger


def main():
    parser = argparse.ArgumentParser(
        description="AutoClip - Automatic Video Highlight Clipping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input video file path or YouTube URL'
    )

    parser.add_argument(
        '--output', '-o',
        default='./output',
        help='Output directory for clips (default: ./output)'
    )

    parser.add_argument(
        '--max-clips', '-n',
        type=int,
        default=5,
        help='Maximum number of clips to generate (default: 5)'
    )

    parser.add_argument(
        '--clip-duration', '-d',
        type=int,
        default=30,
        help='Maximum duration for each clip in seconds (default: 30)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--aspect',
        default='16:9',
        help='Output aspect ratio (default: 16:9)'
    )

    parser.add_argument(
        '--config',
        default='config/settings.json',
        help='Path to configuration file (default: config/settings.json)'
    )

    parser.add_argument(
        '--subtitle',
        choices=['none', 'tiktok', 'classic'],
        default='tiktok',
        help='Subtitle style (default: tiktok)'
    )

    parser.add_argument(
        '--project-name', '-p',
        default='Untitled',
        help='Project name for clip naming (default: Untitled)'
    )

    parser.add_argument(
        '--enable-crop',
        type=str,
        default='true',
        help='Enable crop to 16:9 aspect ratio (true/false, default: true)'
    )

    parser.add_argument(
        '--quality',
        choices=['draft', 'balanced', 'high'],
        default='balanced',
        help='Encoding quality preset (draft/balanced/high, default: balanced)'
    )

    parser.add_argument(
        '--subtitle-style',
        choices=['tiktok', 'classic'],
        default='tiktok',
        help='Subtitle style (default: tiktok)'
    )

    parser.add_argument(
        '--subtitle-position',
        choices=['center', 'bottom'],
        default='center',
        help='Subtitle position (default: center)'
    )

    parser.add_argument(
        '--subtitle-color',
        choices=['white', 'yellow', 'cyan'],
        default='white',
        help='Subtitle color (default: white)'
    )

    parser.add_argument(
        '--subtitle-uppercase',
        action='store_true',
        default=True,
        help='Use uppercase subtitles (default: True)'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = 'DEBUG' if args.verbose else 'INFO'
    logger = StructuredLogger(log_level).get_logger()

    try:
        logger.info("Starting AutoClip Engine")
        logger.info(f"Input: {args.input}")
        logger.info(f"Output: {args.output}")

        # Update config with aspect ratio
        with open(args.config, 'r') as f:
            config = json.load(f)

        config['crop']['aspect_ratio'] = args.aspect

        # Update subtitle config
        config['subtitle']['enabled'] = args.subtitle != 'none'
        config['subtitle']['style'] = args.subtitle_style
        config['subtitle']['position'] = args.subtitle_position
        config['subtitle']['color'] = args.subtitle_color
        config['subtitle']['uppercase'] = getattr(args, 'subtitle_uppercase', True)

        # Add project name to config
        config['project_name'] = args.project_name

        # Parse enable_crop (string to boolean)
        enable_crop = args.enable_crop.lower() == 'true'
        config['enable_crop'] = enable_crop

        # Quality preset to CRF mapping
        quality_crf_map = {
            'draft': 28,      # Fast, larger file
            'balanced': 23,   # Recommended (default)
            'high': 18        # Slower, better quality, smaller file
        }
        crf_value = quality_crf_map.get(args.quality, 23)
        config['ffmpeg']['crf'] = crf_value

        # Save updated config
        with open(args.config, 'w') as f:
            json.dump(config, f, indent=2)

        # Initialize pipeline
        pipeline = AutoClipPipeline(args.config)

        # Process video
        result = pipeline.process(
            input_source=args.input,
            output_dir=args.output,
            max_clips=args.max_clips,
            clip_duration=args.clip_duration,
            project_name=args.project_name,
            enable_crop=enable_crop
        )

        # Print final summary to stdout (for UI consumption)
        print(json.dumps({
            "type": "complete",
            "result": result
        }))

        logger.info("AutoClip processing completed successfully")
        return 0

    except KeyboardInterrupt:
        ProgressEmitter.emit_error("Process interrupted by user")
        logger.warning("Process interrupted")
        return 1

    except Exception as e:
        error_msg = f"Engine failed: {str(e)}"
        ProgressEmitter.emit_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())