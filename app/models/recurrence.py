"""Shared recurrence pattern definitions and validation"""
from enum import Enum
from typing import Optional, Set, Annotated
from pydantic import AfterValidator


class RecurrencePattern(str, Enum):
    """Valid recurrence patterns for recurring tasks"""
    EVERY_DAY = "EVERY_DAY"
    EVERY_WEEK = "EVERY_WEEK"
    EVERY_MONTH = "EVERY_MONTH"
    EVERY_YEAR = "EVERY_YEAR"
    EVERY_MONDAY = "EVERY_MONDAY"
    EVERY_TUESDAY = "EVERY_TUESDAY"
    EVERY_WEDNESDAY = "EVERY_WEDNESDAY"
    EVERY_THURSDAY = "EVERY_THURSDAY"
    EVERY_FRIDAY = "EVERY_FRIDAY"
    EVERY_SATURDAY = "EVERY_SATURDAY"
    EVERY_SUNDAY = "EVERY_SUNDAY"


# Set of valid pattern strings for quick lookups
VALID_RECURRENCE_PATTERNS: Set[str] = {p.value for p in RecurrencePattern}


def validate_recurrence_pattern(value: Optional[str]) -> Optional[str]:
    """
    Validate a recurrence pattern string (supports comma-separated patterns).
    
    Args:
        value: Pattern string like "EVERY_DAY" or "EVERY_MONDAY, EVERY_FRIDAY"
    
    Returns:
        The validated pattern string
    
    Raises:
        ValueError: If any pattern is invalid
    """
    if value is None:
        return value
    
    patterns = [p.strip() for p in value.split(',')]
    
    for pattern in patterns:
        if pattern not in VALID_RECURRENCE_PATTERNS:
            raise ValueError(
                f"Invalid recurrence_pattern: '{pattern}'. "
                f"Valid patterns are: {', '.join(sorted(VALID_RECURRENCE_PATTERNS))}"
            )
    
    return value


# Pydantic annotated types for use in models
ValidatedRecurrencePattern = Annotated[str, AfterValidator(validate_recurrence_pattern)]
OptionalRecurrencePattern = Annotated[Optional[str], AfterValidator(validate_recurrence_pattern)]
