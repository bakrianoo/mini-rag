from helpers.config import get_settings,Settings
import os
import random
import string

class BaseCotroller:
    def __init__(self):
        self.app_settings=get_settings()
        self.base_dire=os.path.dirname(os.path.dirname(__file__))
        self.file_dire=os.path.join( self.base_dire,"assets/files")

    def generate_random_string(self, length: int=12):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    