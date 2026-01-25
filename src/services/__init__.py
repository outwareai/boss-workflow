"""
Services for business logic.
"""

from .attendance import AttendanceService, get_attendance_service
from .documentation_generator import DocumentationGenerator, get_documentation_generator

__all__ = [
    "AttendanceService",
    "get_attendance_service",
    "DocumentationGenerator",
    "get_documentation_generator",
]
