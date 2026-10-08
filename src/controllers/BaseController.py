import random
import string

from helpers.config import get_settings,Settings
import os
from pathlib import Path
class BaseController:
    def __init__(self):
        self.app_settings = get_settings()
        self.base_dir = Path(__file__).parents[1] # src dir
        self.files_dir = os.path.join(
            self.base_dir,
            'assets/files'
        )
        self.database_dir = os.path.join(
            self.base_dir,
            'assets/database'
        )
    def generate_random_string(self, length: int=12):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    def get_database_path(self,db_name:str):
        database_path =  os.path.join(
            self.database_dir,
            db_name
        )
        os.makedirs(
            database_path,exist_ok=True
        )
        return database_path