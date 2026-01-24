"""Custom exceptions for database operations."""


class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Database connection failed."""
    pass


class DatabaseConstraintError(DatabaseError):
    """Database constraint violation (duplicate, foreign key, etc)."""
    pass


class DatabaseOperationError(DatabaseError):
    """General database operation failed."""
    pass


class EntityNotFoundError(DatabaseError):
    """Requested entity not found."""
    pass


class ValidationError(DatabaseError):
    """Data validation failed before database operation."""
    pass
