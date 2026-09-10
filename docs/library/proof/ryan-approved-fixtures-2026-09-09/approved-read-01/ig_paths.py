import pytest
@pytest.fixture
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp("t")
