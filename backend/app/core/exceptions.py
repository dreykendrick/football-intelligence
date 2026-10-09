class FootballIntelligenceException(Exception):
    """Base exception for all system errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DatabaseConnectionError(FootballIntelligenceException):
    """Raised when database connectivity fails."""
    def __init__(self, message: str = "Failed to connect to PostgreSQL database."):
        super().__init__(message, code="DATABASE_CONNECTION_ERROR")


class DataLeakageError(FootballIntelligenceException):
    """Raised when temporal anti-leakage guards detect future data in pre-match feature calculation."""
    def __init__(self, message: str = "Temporal leakage detected: feature relies on future data."):
        super().__init__(message, code="DATA_LEAKAGE_ERROR")


class UnmappedTeamAliasError(FootballIntelligenceException):
    """Raised when raw team name cannot be resolved to canonical internal UUID."""
    def __init__(self, raw_team_name: str, provider_name: str):
        message = f"Unmapped team alias '{raw_team_name}' for provider '{provider_name}'."
        super().__init__(message, code="UNMAPPED_TEAM_ALIAS")
        self.raw_team_name = raw_team_name
        self.provider_name = provider_name
