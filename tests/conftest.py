import warnings
import pytest


@pytest.fixture(autouse=True)
def suppress_forkpty_warning():
    # Suppress forkpty warning
    warnings.filterwarnings("ignore", 
                          category=DeprecationWarning,
                          message="This process .* is multi-threaded")
    yield
    warnings.resetwarnings()
