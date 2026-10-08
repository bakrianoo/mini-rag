from fastapi import FastAPI,APIRouter,Depends,UploadFile,status,Request
from fastapi.responses import JSONResponse
from helpers.config import get_settings,Settings
from controllers import DataController,ProjectController,ProcessController
import os
import aiofiles
from models import ResponseEnum
import logging
from .schemes.data import ProcessRequest
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from models.db_schemes import DataChunk,Asset
from models.AssetModel import AssetModel
from models import AssetTypeEnum

logger = logging.getLogger('uvicorn.error')

data_router = APIRouter(
    prefix='/api/v1/data',
    tags=['api_v1','data']
)


'''
Use POST when the client wants to send data to the server, often to create something or perform an operation.
'''
@data_router.post('/upload/{project_id}')
async def upload_data(request:Request,
                      project_id:str,
                      file:UploadFile,
                      app_settings:Settings = Depends(get_settings)
                      ):
    # print("filename:", file.filename)
    # print("content_type:", file.content_type)
    # print("allowed:", app_settings.FILE_ALLOWED_TYPES)
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )
    project = await project_model.get_or_create_project(
        project_id=project_id
    )
    is_valid,result_signal = DataController().validate_uploading_files(file=file)
    if not is_valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal" : result_signal
            }
        )
    file_path,file_id = DataController().generate_unique_file_path(file.filename,project_id)
    try:
        async with aiofiles.open(file_path , 'wb') as f:
            while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                await f.write(chunk)
    except Exception as e:
        logger.error(f'error while uploading file, {e} ')
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                'signal':ResponseEnum.FILE_UPLOAD_FAIL.value
            }
        )

    asset_model = await AssetModel.create_instance(
        db_client=request.app.db_client
    )

    asset = Asset(
        asset_project_id=project.id,
        asset_type = AssetTypeEnum.FILE.value,
        asset_name = file_id,
        asset_size = os.path.getsize(file_path),
    )

    asset_record = await asset_model.create_asset(asset)
    
    return JSONResponse(
        content={
            'signal':ResponseEnum.FILE_UPLOAD_SUCCESS.value,
            'database_file_id':str(asset_record.id)
        }
    )

@data_router.post('/process/{project_id}')
async def process_endpoint(request:Request,project_id:str,process_request:ProcessRequest):
    project_model = await ProjectModel.create_instance(
            db_client=request.app.db_client
    )

    project = await project_model.get_or_create_project(
        project_id=project_id
    )

    chunk_model = await ChunkModel.create_instance(
        db_client=request.app.db_client
    )
    asset_model = await AssetModel.create_instance(
                db_client=request.app.db_client
    )
    project_files_ids = {}
    if process_request.file_id:
        asset = await asset_model.get_asset_record(
            asset_project_id=project.id,
            asset_name=process_request.file_id
        )

        if asset is None:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    'signal':ResponseEnum.FILE_ID_ERROR.value
                }
            )

        project_files_ids[asset.id] = asset.asset_name
    else:
        assets = await asset_model.get_all_project_assets(
            asset_project_id=str(project.id),
            asset_type=AssetTypeEnum.FILE.value
        )

        project_files_ids = {
            asset.id : asset.asset_name
            for asset in assets
        }

    if len(project_files_ids) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                'signal':ResponseEnum.NO_FILE_ERROR.value
            }
        )
    
    chunk_size = process_request.chunk_size
    overlap_size = process_request.overlap_size
    reset = process_request.reset
    process_controller = ProcessController(project_id=project_id)
    no_records = 0
    no_processed_files = 0
    if reset:
        _ = await chunk_model.delete_chunks_by_project_id(project_id=project.id)
    for asset_id,file_id in project_files_ids.items():  
        file_content = process_controller.get_file_content(file_id=file_id)
        if file_content is None:
            logger.error(f'Error while processing file: {file_id}')
            continue
        file_chunks = process_controller.process_file_content(
            file_content=file_content,
            file_id=file_id,
            chunk_size=chunk_size,
            overlap_size=overlap_size
        )
        if file_chunks is None or len(file_chunks) == 0:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    'signal':ResponseEnum.PROCESSING_FAIL.value
                }
            )
        
        chunk_list = [
            DataChunk(
                chunk_text = chunk.page_content ,
                chunk_metadata = chunk.metadata ,
                chunk_order = i+1,
                chunk_project_id = project.id,
                chunk_asset_id=asset_id
            )
            for i,chunk in enumerate(file_chunks)
        ]

        no_records +=  await chunk_model.insert_many_chunks(chunk_list)
        no_processed_files+=1
    
    
    return JSONResponse(
        content={
            "signal" : ResponseEnum.PROCESSING_SUCCESS.value,
            'chunks_inserted' : no_records,
            'processed_files':no_processed_files
        }
    )
    
    