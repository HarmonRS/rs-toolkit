"""GF3 L1A to L2 processing pipeline."""

__all__ = ["PipelineConfig", "run_pipeline"]
__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "PipelineConfig":
        from gf3_l1a2l2.config import PipelineConfig

        return PipelineConfig
    if name == "run_pipeline":
        from gf3_l1a2l2.pipeline import run_pipeline

        return run_pipeline
    raise AttributeError(name)
