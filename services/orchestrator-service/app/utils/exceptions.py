class OrchestratorError(Exception):
    """Base class for orchestrator domain errors (routes map these to HTTP)."""


class SessionNotFound(OrchestratorError):
    pass


class NotSessionOwner(OrchestratorError):
    pass


class SessionClosed(OrchestratorError):
    pass


class PipelineError(OrchestratorError):
    """A downstream stage (STT/LLM/TTS) failed."""
