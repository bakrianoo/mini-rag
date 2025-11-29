from helpers.config import get_settings, Settings
import os
import random
import string

class BaseController:
    
    def __init__(self):
        self.app_settings = get_settings()
        self.base_path = os.path.dirname(os.path.dirname(__file__))
        self.files_path = os.path.join(self.base_path, "assets/files")


    def generate_random_string(self, length: int = 12):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))