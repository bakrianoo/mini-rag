from .BaseController import BaseCotroller
from fastapi import UploadFile
from models import ResponsFiles
import os

class ProjectController(BaseCotroller):
    def __init__(self):
        super().__init__()

    def get_project_path(self,project_id: str):
        projectpath=os.path.join(self.file_dire,project_id)
        if not os.path.exists(projectpath):
            os.makedirs(projectpath)
        return projectpath