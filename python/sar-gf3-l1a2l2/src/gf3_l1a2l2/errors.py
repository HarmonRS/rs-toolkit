class GF3PipelineError(Exception):
    """Base error for pipeline failures."""


class DiscoveryError(GF3PipelineError):
    """Raised when input products cannot be discovered."""


class MetadataError(GF3PipelineError):
    """Raised when GF3 metadata cannot be parsed."""


class RpcError(GF3PipelineError):
    """Raised when RPC metadata cannot be parsed."""


class ProcessingError(GF3PipelineError):
    """Raised when image processing fails."""
