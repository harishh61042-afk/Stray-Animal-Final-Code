"""The optional offline-libraries downloader (tools/download_vendor.py). No network is used: downloads are faked."""
import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_tool(name):
    """Import a script from tools/ by its file name (tools/ is a folder of scripts, not a package)."""
    spec = importlib.util.spec_from_file_location(f"pawconnect_tool_{name}", ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_dictionary(name):
    """A dictionary literal from app/template_utils.py, read without importing the Flask code around it."""
    tree = ast.parse((ROOT / "app" / "template_utils.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} was not found in app/template_utils.py")


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self.data


@pytest.fixture()
def tool(tmp_path, monkeypatch):
    module = load_tool("download_vendor")
    monkeypatch.setattr(module, "VENDOR", tmp_path / "vendor")
    return module


# ------------------------------------------------------------------ the list of files
def test_the_offline_files_are_the_ones_the_pages_load_from_the_cdn(tool):
    cdn, local = read_dictionary("CDN"), read_dictionary("LOCAL_VENDOR")
    for key, path in local.items():
        if path is None:  # the web font is simply skipped in offline mode
            continue
        relative = path.removeprefix("vendor/")
        assert relative in tool.FILES, f"{path} is used by the pages but the downloader does not fetch it"
        assert tool.FILES[relative] == cdn[key], f"{key}: the downloader and the pages use different versions"


def test_map_pictures_and_icon_fonts_are_included(tool):
    assert "leaflet/images/marker-icon.png" in tool.FILES  # the CSS of these libraries loads them by relative path
    assert "bootstrap-icons/fonts/bootstrap-icons.woff2" in tool.FILES


# ------------------------------------------------------------------ downloading
def test_every_file_is_saved_where_the_pages_expect_it(tool, monkeypatch, capsys):
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda request, timeout=None: FakeResponse(b"data"))
    assert tool.main([]) == 0
    for relative in tool.FILES:
        assert (tool.VENDOR / relative).read_bytes() == b"data"
    assert "USE_LOCAL_VENDOR=1" in capsys.readouterr().out


def test_files_that_are_already_there_are_kept_unless_forced(tool, monkeypatch):
    target = tool.VENDOR / "leaflet" / "leaflet.js"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda request, timeout=None: FakeResponse(b"new"))

    assert tool.main([]) == 0
    assert target.read_bytes() == b"old"
    assert tool.main(["--force"]) == 0
    assert target.read_bytes() == b"new"


def test_a_failed_download_is_reported_and_the_others_continue(tool, monkeypatch, capsys):
    def flaky(request, timeout=None):
        if "leaflet.css" in request.full_url:
            raise OSError("no connection")
        return FakeResponse(b"data")

    monkeypatch.setattr(tool.urllib.request, "urlopen", flaky)
    assert tool.main([]) == 1  # the exit status tells a script that something is missing
    output = capsys.readouterr().out
    assert "FAILED" in output and "leaflet/leaflet.css" in output
    assert not (tool.VENDOR / "leaflet" / "leaflet.css").exists()
    assert (tool.VENDOR / "leaflet" / "leaflet.js").exists()  # the rest was still downloaded


def test_an_empty_answer_is_not_saved_as_a_file(tool, monkeypatch):
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda request, timeout=None: FakeResponse(b""))
    target = tool.VENDOR / "chartjs" / "chart.umd.js"
    with pytest.raises(OSError, match="empty"):
        tool.download("https://example.test/chart.umd.js", target)
    assert not target.exists()
