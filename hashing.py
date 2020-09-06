import hashlib
from tempfile import SpooledTemporaryFile
from zipfile import ZipFile

from witmanager import COMMIT_ID_LENGTH, Text, WitManager


class Hashing:
    @staticmethod
    def by_path(path: str) -> str:
        """Return the file content."""
        with SpooledTemporaryFile() as temp:
            with ZipFile(temp, 'w') as archive:
                for filename in WitManager.get_path_files(path):
                    archive.write(
                        filename
                    )
            temp.seek(0)
            file_content = temp.read()
            file_hash = Hashing.by_content(file_content)
            return file_hash

    @staticmethod  # Credit to lms
    def by_content(file_content: Text) -> str:
        """Create a hexdigest according to the file content.

        In order to compare two same directories contents."""
        if not isinstance(file_content, bytes):
            file_content = file_content.encode('utf-8')
        hashed_name = hashlib.blake2b(digest_size=(COMMIT_ID_LENGTH // 2))
        hashed_name.update(file_content)
        return hashed_name.hexdigest()
