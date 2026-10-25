"""Check wheel and source-distribution contents before publication."""

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

SOURCE_DIRS = {"src", "tests", "docs", "examples", "scripts", ".github"}
SOURCE_FILES = {
    "README.md",
    "README.de.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "uv.lock",
    "requirements.lock",
    "Dockerfile",
    ".dockerignore",
    ".gitignore",
    ".env.example",
    "PKG-INFO",
}
FORBIDDEN_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "backups",
    "snapshots",
}


def check_name(name: str, *, wheel: bool) -> None:
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe archive path: {name}")
    for part in path.parts:
        if part in FORBIDDEN_DIRS:
            raise ValueError(f"Private/generated directory in artifact: {name}")
        if part.startswith(".env") and part != ".env.example":
            raise ValueError(f"Environment file in artifact: {name}")
        if part.endswith((".pem", ".key", ".pyc", ".pyo")) or part == ".DS_Store":
            raise ValueError(f"Private/generated file in artifact: {name}")
    if wheel:
        if path.parts[0] != "plenticore_mcp" and not path.parts[0].endswith(".dist-info"):
            raise ValueError(f"Unexpected wheel member: {name}")
    elif path.parts[0] not in SOURCE_DIRS and name not in SOURCE_FILES:
        raise ValueError(f"Unexpected source member: {name}")


def check_artifact(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = [item.filename for item in archive.infolist() if not item.is_dir()]
        for name in names:
            check_name(name, wheel=True)
        if not any(name.endswith("/licenses/LICENSE") for name in names):
            raise ValueError("Wheel is missing its license")
    elif path.name.endswith(".tar.gz"):
        names = []
        roots = set()
        with tarfile.open(path, "r:gz") as archive:
            for item in archive:
                if item.isdir():
                    continue
                if not item.isfile():
                    raise ValueError(f"Non-regular archive member: {item.name}")
                full = PurePosixPath(item.name)
                if len(full.parts) < 2 or full.is_absolute():
                    raise ValueError(f"Invalid source root: {item.name}")
                roots.add(full.parts[0])
                name = str(PurePosixPath(*full.parts[1:]))
                check_name(name, wheel=False)
                names.append(name)
        if len(roots) != 1 or not {"README.md", "LICENSE", "pyproject.toml"} <= set(names):
            raise ValueError("Source distribution has invalid roots or missing metadata")
    else:
        raise ValueError(f"Unsupported artifact: {path.name}")
    if not names:
        raise ValueError(f"Empty artifact: {path.name}")
    return len(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.artifacts:
        count = check_artifact(path)
        print(f"{path.name}: {count} files; artifact allowlist passed.")


if __name__ == "__main__":
    main()
