from fastapi import FastAPI, APIRouter,Depends
import os
from helpers.config import get_settings, Settings


base_router = APIRouter(
    prefix="/api/v1",
    tags=["api_v1"],
)

@base_router.get("/welcome")
async def welcome(app_settings : Settings=Depends(get_settings)):
     
   
    appname=app_settings.APP_NAME
    appversion=app_settings.APP_VERSION

    return {
        "app_name": appname,
        "app_version": appversion,
    }
