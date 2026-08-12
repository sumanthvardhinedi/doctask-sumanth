from pathlib import Path


class DocumentStore:
    """Resolve PackageDocument.storage_path to local file bytes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def read_bytes(self, storage_path: str) -> bytes:
        candidate = Path(storage_path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.root / candidate).resolve()

        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(
                f"storage_path escapes configured uploads root: {storage_path}"
            ) from exc

        if not resolved.is_file():
            raise FileNotFoundError(f"Document file not found: {storage_path}")

        return resolved.read_bytes()
