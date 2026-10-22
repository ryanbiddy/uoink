"""Wire fixtures accept both supported test layouts and reject live state."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests import mcp_wire


@pytest.fixture
def roots(tmp_path, monkeypatch):
    user = tmp_path / "real-user"
    live = (user / "AppData/Local/Uoink",
            user / "Library/Application Support/Uoink",
            user / ".local/share/Uoink")
    monkeypatch.setattr(mcp_wire, "_USER_HOME", user)
    monkeypatch.setattr(mcp_wire, "_USER_DATA_ROOTS", live)
    monkeypatch.setenv("IG_FORBIDDEN_LIVE", str(live[0] / "index.db"))
    return user, live, tmp_path / "disposable"


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
@pytest.mark.parametrize("layout", ["profile", "profile-with-app", "home", "data-root"])
def test_accepts_disposable_layouts(roots, monkeypatch, platform, layout):
    _, _, temporary = roots
    monkeypatch.setattr(mcp_wire, "sys", SimpleNamespace(platform=platform))
    env = {"HOME": str(temporary / "home"), "USERPROFILE": str(temporary / "home")}
    if layout.startswith("profile"):
        env = {"UOINK_ISOLATED_PROFILE": str(temporary / "profile"),
               "UOINK_ISOLATED_PORT": "43871"}
        if layout == "profile-with-app":
            env["UOINK_ISOLATED_APP_DIR"] = str(temporary / "app")
    elif layout == "data-root":
        env.update(LOCALAPPDATA=str(temporary / "local"),
                   XDG_DATA_HOME=str(temporary / "xdg"))
    before = dict(env)
    mcp_wire._assert_disposable_env(env)
    assert env == before  # Keep normal platform layout and read-only app semantics.


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
@pytest.mark.parametrize("case", ["missing", "home", "profile", "profile-child",
                                  "app", "effective-root", "explicit-live-index",
                                  "relative", "partial-profile", "partial-port"])
def test_refuses_unsafe_layouts_before_launch(roots, monkeypatch, platform, case):
    user, live, temporary = roots
    monkeypatch.setattr(mcp_wire, "sys", SimpleNamespace(platform=platform))
    env = {"UOINK_ISOLATED_PROFILE": str(temporary / "profile"),
           "UOINK_ISOLATED_PORT": "43871"}
    if case == "missing":
        env = {}
    elif case == "home":
        env = {"HOME": str(user), "USERPROFILE": str(user)}
    elif case == "profile":
        env["UOINK_ISOLATED_PROFILE"] = str(live[0])
    elif case == "profile-child":
        env["UOINK_ISOLATED_PROFILE"] = str(live[0] / "nested")
    elif case == "app":
        env["UOINK_ISOLATED_APP_DIR"] = str(live[0])
    elif case == "effective-root":
        env = {"HOME": str(temporary / "home"), "USERPROFILE": str(temporary / "home"),
               "LOCALAPPDATA": str(live[0].parent), "XDG_DATA_HOME": str(live[2].parent)}
        if platform == "darwin":
            env["HOME"] = str(user)
    elif case == "explicit-live-index":
        env["IG_FORBIDDEN_LIVE"] = str(temporary / "profile/index.db")
    elif case == "relative":
        env["UOINK_ISOLATED_PROFILE"] = "relative-profile"
    elif case == "partial-profile":
        env.pop("UOINK_ISOLATED_PORT")
    else:
        env.pop("UOINK_ISOLATED_PROFILE")
    popen = Mock()
    monkeypatch.setattr(mcp_wire.subprocess, "Popen", popen)
    with pytest.raises(AssertionError):
        mcp_wire.StdioClient(["unused"], temporary, env)
    popen.assert_not_called()


@pytest.mark.parametrize("port", ["5179", "05179", " 5179 ", "0", "-1", "65536", "", "invalid"])
@pytest.mark.parametrize("profile", [False, True])
def test_refuses_unsafe_ports_even_with_temporary_home(roots, monkeypatch, port, profile):
    _, _, temporary = roots
    env = {"HOME": str(temporary), "USERPROFILE": str(temporary),
           "UOINK_ISOLATED_PORT": port}
    if profile:
        env["UOINK_ISOLATED_PROFILE"] = str(temporary / "profile")
    popen = Mock()
    monkeypatch.setattr(mcp_wire.subprocess, "Popen", popen)
    with pytest.raises(AssertionError, match="port"):
        mcp_wire.StdioClient(["unused"], temporary, env)
    popen.assert_not_called()
