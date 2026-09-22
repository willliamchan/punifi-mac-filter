"""Check release layout, links, metadata and common accidental-secret patterns."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "punifi_macfilter"
paths = (
    subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    .decode()
    .split("\0")
)
paths = sorted({name for name in paths if name})
assert [p.name for p in (ROOT / "custom_components").iterdir() if p.is_dir() and p.name != "__pycache__"] == [
    "punifi_macfilter"
]
manifest = json.loads((COMPONENT / "manifest.json").read_text())
assert manifest["domain"] == "punifi_macfilter" and manifest["config_flow"] is True
assert manifest["codeowners"] == ["@willliamchan"]
assert json.loads((ROOT / "hacs.json").read_text())["homeassistant"] == "2026.9.3"
assert (COMPONENT / "brand/icon.png").is_file()
assert json.loads((COMPONENT / "strings.json").read_text()) == json.loads(
    (COMPONENT / "translations/en.json").read_text()
)
links = 0
for name in paths:
    path = ROOT / name
    assert not any(
        part in {".venv", ".storage", "__pycache__", "secrets", "private", "backups"}
        for part in path.relative_to(ROOT).parts
    ), name
    assert path.name not in {".env", "secrets.yaml", "WORK_PLAN.md", "CHECKPOINT.md"}, name
    if path.suffix == ".png":
        continue
    text = path.read_text()
    assert not re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text), name
    assert not re.search(r"gh[pousr]_[A-Za-z0-9]{30,}", text), name
    if path.suffix != ".md":
        continue
    for destination in re.findall(r"\]\(([^)]+)\)", text):
        if destination.startswith(("http:", "https:")):
            continue
        target, _, anchor = destination.partition("#")
        resolved = (path.parent / target).resolve() if target else path
        assert resolved.is_relative_to(ROOT) and resolved.is_file(), (name, destination)
        if anchor:
            headings = re.findall(r"^#+ (.+)$", resolved.read_text(), re.M)
            anchors = [re.sub(r"[^\w\- ]", "", s.lower()).replace(" ", "-") for s in headings]
            assert anchor in anchors, (name, destination)
        links += 1
print(
    f"PASS: {len(paths)} repository files; {links} local links/anchors; metadata, translations and secret-pattern checks."
)
