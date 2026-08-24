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
            # DB paths are stored relative to the backend project root,
            # e.g. "uploads/cover_letter.pdf". Since root is already the
            # configured uploads directory, strip that leading directory.
            parts = candidate.parts
            root_name = self.root.name

            if parts and parts[0].lower() == root_name.lower():
                candidate = Path(*parts[1:])

            resolved = (self.root / candidate).resolve()

        print(
    f"[DocumentStore] root={self.root} "
    f"storage_path={storage_path} "
    f"resolved={resolved} "
    f"exists={resolved.is_file()}"
)

        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(
                f"storage_path escapes configured uploads root: {storage_path}"
            ) from exc

        if not resolved.is_file():
            raise FileNotFoundError(
                f"Document file not found: {storage_path}"
            )

        return resolved.read_bytes()