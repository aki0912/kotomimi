class EvaluationConfigError(ValueError):
    """A registry or suite configuration is invalid."""


class LicensePolicyError(EvaluationConfigError):
    """A dataset is not authorized by the evaluation-data policy."""


class ApprovalError(LicensePolicyError):
    """A manual-review approval is missing or invalid."""


class DatasetPreparationError(RuntimeError):
    """Downloaded or prepared dataset content failed validation."""


class ModelEvaluationUnavailable(RuntimeError):
    """An optional model-backed evaluation cannot run in this environment."""
