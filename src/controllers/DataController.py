from .BaseController import BaseCotroller
from fastapi import FastAPI, APIRouter,Depends,UploadFile
from models import ResponsFiles
from .ProjectController import ProjectController
import re
import os


class DataController(BaseCotroller):
    def __init__(self):
        self.ResponsFiles=ResponsFiles
        super().__init__()
        self.size_scale=1048576 # convert to MB from byte
    
    def validate_uploaded_file(self,file:UploadFile):
        if file.content_type not in self.app_settings.FILE_ALLOWED_TYPES:
            return False,ResponsFiles.File_Type_Not_Supported.value
        if file.size>self.app_settings.FILE_MAX_SIZE*self.size_scale:
            return False,ResponsFiles.File_Size_Exceedee.value
        
        return True,ResponsFiles.File_upload_sucess.value
    
    def generate_file_name(self,origin_filename:str,projectid: str):
        rand_file_Key=self.generate_random_string()
        project_path=ProjectController().get_project_path(project_id=projectid)
        cleaende_filename=self.get_clean_file_name(orig_file_name=origin_filename)
        final_file_path= os.path.join(
project_path,rand_file_Key+"_"+cleaende_filename
        )
        while os.path.exists(final_file_path):
             rand_file_Key=self.generate_random_string()
        project_path=ProjectController().get_project_path(project_id=projectid)
        cleaende_filename=self.get_clean_file_name(orig_file_name=origin_filename)
        final_file_path= os.path.join(
project_path, rand_file_Key+"_"+cleaende_filename
        )


        return final_file_path

    def get_clean_file_name(self, orig_file_name: str):

        # remove any special characters, except underscore and .
        cleaned_file_name = re.sub(r'[^\w.]', '', orig_file_name.strip())

        # replace spaces with underscore
        cleaned_file_name = cleaned_file_name.replace(" ", "_")

        return cleaned_file_name