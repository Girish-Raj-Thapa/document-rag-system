import os 
import shutil
from abc import ABC, abstractmethod
from typing import BinaryIO
from fastapi import UploadFile
from app.core.config import get_settings


class StorageProvider(ABC):
    """
    Abstract base class for document storage strategies.
    """

    @abstractmethod
    async def upload_file(self, workspace_id: str, stored_filename: str, file: UploadFile) -> str:
        """
        Uploads a file and returns the storage path/URI.
        """
        pass

    
    @abstractmethod
    def get_file_path(self, storage_path: str) -> str:
        """
        Returns the absolute or reachable path/URI for a stored file.
        """
        pass


    @abstractmethod
    def delete_file(self, storage_path: str) -> None:
        """
        Deletes a file from storage.
        """
        pass


class LocalStorageProvider(StorageProvider):
    """
    Local disk implementation of the storage provider.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.base_dir = self.settings.STORAGE_PATH
        os.makedirs(self.base_dir, exist_ok=True)
    

    def _get_workspace_dir(self, workspace_id: str) -> str:
        workspace_dir = os.path.join(self.base_dir, str(workspace_id), "documents")
        os.makedirs(workspace_dir, exist_ok=True)
        return workspace_dir


    async def upload_file(self, workspace_id: str, stored_filename: str, file: UploadFile) -> str:
        workspace_dir = self._get_workspace_dir(workspace_id)
        file_path = os.path.join(workspace_dir, stored_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return file_path


    def get_file_path(self, storage_path: str) -> str:
        return storage_path


    def delete_file(self, storage_path: str) -> None:
        if os.path.exists(storage_path):
            os.remove(storage_path)


def get_storage_provider() -> StorageProvider:
    """
    Factory function to get the configured storage provider. Injected via Depends.
    """
    return LocalStorageProvider()
