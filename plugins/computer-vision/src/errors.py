"""Structured error types and response factories for the CV plugin."""

from __future__ import annotations

from typing import Any

# Error code constants
WINDOW_NOT_FOUND = "WINDOW_NOT_FOUND"
WINDOW_MINIMIZED = "WINDOW_MINIMIZED"
ACCESS_DENIED = "ACCESS_DENIED"
SCREEN_LOCKED = "SCREEN_LOCKED"
TIMEOUT = "TIMEOUT"
INVALID_COORDINATES = "INVALID_COORDINATES"
OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
RATE_LIMITED = "RATE_LIMITED"
DRY_RUN = "DRY_RUN"
INVALID_INPUT = "INVALID_INPUT"
CAPTURE_FAILED = "CAPTURE_FAILED"
INPUT_FAILED = "INPUT_FAILED"
UIA_ERROR = "UIA_ERROR"
FIND_NO_MATCH = "FIND_NO_MATCH"
OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"


def make_error(code: str, message: str) -> dict[str, Any]:
    """Create a structured error response."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


def make_success(**payload: Any) -> dict[str, Any]:
    """Create a structured success response."""
    return {"success": True, **payload}


class CVPluginError(Exception):
    """Base exception for CV plugin errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return make_error(self.code, self.message)


class WindowNotFoundError(CVPluginError):
    def __init__(self, hwnd: int) -> None:
        super().__init__(WINDOW_NOT_FOUND, f"Window with HWND {hwnd} no longer exists")


class AccessDeniedError(CVPluginError):
    def __init__(self, process_name: str) -> None:
        super().__init__(ACCESS_DENIED, f"Access denied: process '{process_name}' is restricted")


class RateLimitedError(CVPluginError):
    def __init__(self) -> None:
        super().__init__(RATE_LIMITED, "Rate limit exceeded. Max 20 input actions per second.")


class InvalidCoordinatesError(CVPluginError):
    def __init__(self, x: int, y: int) -> None:
        super().__init__(INVALID_COORDINATES, f"Coordinates ({x}, {y}) outside virtual desktop bounds")
