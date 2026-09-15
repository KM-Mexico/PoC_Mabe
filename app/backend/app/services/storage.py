from pathlib import Path
from unicodedata import normalize
from uuid import UUID, uuid4


class PrivateDocumentStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def normalize_original_name(value: str | None) -> str:
        raw_name = (value or "document").replace("\\", "/").rsplit("/", 1)[-1]
        normalized = normalize("NFKC", raw_name)
        safe = "".join(character if character.isprintable() and character not in '<>:"/\\|?*' else "_" for character in normalized)
        safe = safe.strip(" ._")[:180]
        return safe or "document"

    def write(self, content: bytes) -> str:
        storage_name = str(uuid4())
        destination = self._path(storage_name)
        destination.write_bytes(content)
        destination.chmod(0o600)
        return storage_name

    def delete(self, storage_name: str) -> None:
        path = self._path(storage_name)
        path.unlink(missing_ok=True)

    def _path(self, storage_name: str) -> Path:
        UUID(storage_name)
        candidate = (self.root / storage_name).resolve()
        if candidate.parent != self.root:
            raise ValueError("Invalid storage path")
        return candidate
