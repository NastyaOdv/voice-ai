class AuthError(Exception):
    """Base class for auth domain errors (routes map these to HTTP responses)."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class InvalidToken(AuthError):
    pass


class PasswordNotSet(AuthError):
    """The account has no local password (e.g. a Google-only account)."""
