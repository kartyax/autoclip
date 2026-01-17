import json
import sys
from typing import Dict, Any


class ProgressEmitter:
    """Emit progress, logs, and errors as JSON to stdout"""

    @staticmethod
    def emit_progress(step: str, percent: int, **kwargs):
        """Emit progress update"""
        data = {
            "type": "progress",
            "step": step,
            "percent": percent,
            **kwargs
        }
        print(f"IPC_EVENT:{json.dumps(data)}", flush=True)

    @staticmethod
    def emit_log(level: str, message: str, **kwargs):
        """Emit log message"""
        data = {
            "type": "log",
            "level": level.upper(),
            "message": message,
            **kwargs
        }
        print(f"IPC_EVENT:{json.dumps(data)}", flush=True)

    @staticmethod
    def emit_error(message: str, **kwargs):
        """Emit error message"""
        data = {
            "type": "error",
            "message": message,
            **kwargs
        }
        print(f"IPC_EVENT:{json.dumps(data)}", flush=True)

    @staticmethod
    def emit_clip(file: str, duration: int, **kwargs):
        """Emit clip creation event"""
        data = {
            "type": "clip",
            "file": file,
            "duration": duration,
            **kwargs
        }
        print(f"IPC_EVENT:{json.dumps(data)}", flush=True)

    @staticmethod
    def emit_subtitle(clip: str, subtitle: str, **kwargs):
        """Emit subtitle creation event"""
        data = {
            "type": "subtitle",
            "clip": clip,
            "subtitle": subtitle,
            **kwargs
        }
        print(f"IPC_EVENT:{json.dumps(data)}", flush=True)

    @staticmethod
    def emit_state(status: str, **kwargs):
        """Emit state change event"""
        data = {
            "type": "state",
            "status": status,
            **kwargs
        }
        print(f"IPC_EVENT:{json.dumps(data)}", flush=True)

    @staticmethod
    def emit_complete(total_clips: int, **kwargs):
        """Emit completion event"""
        data = {
            "type": "complete",
            "total_clips": total_clips,
            **kwargs
        }
        print(f"IPC_EVENT:{json.dumps(data)}", flush=True)