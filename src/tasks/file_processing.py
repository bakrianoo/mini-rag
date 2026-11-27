from celery_app import celery_app, get_setup_utils
from helpers.config import get_settings
import asyncio
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from models.AssetModel import AssetModel
from models.db_schemes import DataChunk
from models import ResponseSignal
from models.enums.AssetTypeEnum import AssetTypeEnum
from controllers import ProcessController
from controllers import NLPController
from utils.idempotency_manager import IdempotencyManager, TaskInProgress
from models.enums.DataBaseEnum import DataBaseEnum
import logging
logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Permanent failure: retrying will not help."""


@celery_app.task(
                 bind=True, name="tasks.file_processing.process_project_files",
                 autoretry_for=(Exception,),
                 dont_autoretry_for=(ValueError, LookupError, ProcessingError),
                 retry_kwargs={'max_retries': 3, 'countdown': 60}
                )
def process_project_files(self, project_id: int, 
                          file_id: int, chunk_size: int,
                          overlap_size: int, do_reset: int,  card_id: int):

    return asyncio.run(
        _process_project_files(self, project_id, file_id, chunk_size,
                               overlap_size, do_reset,card_id)
    )


async def _process_project_files(task_instance, project_id: int, 
                                 file_id: int, chunk_size: int,
                                 overlap_size: int, do_reset: int,card_id: int):

    
    db_engine, vectordb_client = None, None
    execution_id = None
    
    try:

        (db_engine, db_client, llm_provider_factory, 
        vectordb_provider_factory,
        generation_client, embedding_client,
        vectordb_client, template_parser) = await get_setup_utils()

        # Create idempotency manager
        idempotency_manager = IdempotencyManager(db_client, db_engine)

        # Define task arguments for idempotency check
        task_args = {
            "project_id": project_id,
            "file_id": file_id,
            "chunk_size": chunk_size,
            "overlap_size": overlap_size,
            "do_reset": do_reset,
            "card_id": card_id
        }
        
        task_name = "tasks.file_processing.process_project_files"

        settings = get_settings()

        # Atomic claim: (task_name, celery_task_id). A retry has the same id.
        execution_id, existing_task = await idempotency_manager.claim_task(
            task_name=task_name,
            task_args=task_args,
            celery_task_id=task_instance.request.id,
            lease_seconds=settings.CELERY_TASK_TIME_LIMIT + 60
        )

        if execution_id is None:
            if existing_task is not None and existing_task.status == 'SUCCESS' and existing_task.result:
                logger.warning("Task already succeeded, returning stored result")
                return existing_task.result

            # still running somewhere else: retry later instead of returning None
            raise TaskInProgress(
                f"task is owned by another worker | status: "
                f"{existing_task.status if existing_task else None}"
            )

        project_model = await ProjectModel.create_instance(
            db_client=db_client
        )

        project = await project_model.get_project_by_id(project_id)

        if project is None:
          raise LookupError(f"Project {project_id} does not exist.")

        project_id = project.project_id

        nlp_controller = NLPController(
            vectordb_client=vectordb_client,
            generation_client=generation_client,
            embedding_client=embedding_client,
            template_parser=template_parser,
        )

        asset_model = await AssetModel.create_instance(
                db_client=db_client
            )
        project_files_ids = {}

        if file_id:
            try:
                asset_id = int(file_id)
            except (TypeError, ValueError):
                raise ValueError("Invalid file_id.")

            asset_record = await asset_model.get_asset_by_id(
                project_id=project.project_id,
                asset_id=asset_id,
            )

            if asset_record is None:
                raise LookupError(
                    f"File {asset_id} does not belong to project {project.project_id}."
                )

            project_files_ids = {
                asset_record.asset_id: asset_record.asset_name
            }
        else:
            assets = await asset_model.get_all_project_assets(
                asset_project_id=project.project_id,
                asset_type=AssetTypeEnum.FILE.value,
            )
            project_files_ids = {
                asset.asset_id: asset.asset_name
                for asset in assets
            }
        

        if len(project_files_ids) == 0:
            raise ProcessingError(f"No files found for project_id: {project.project_id}")
        
        process_controller = ProcessController(project_id=project_id)

        no_records = 0
        no_files = 0

        chunk_model = await ChunkModel.create_instance(
                            db_client=db_client
                        )

        collection_name = nlp_controller.create_collection_name(project_id=project.project_id)

        requested_asset_id = int(file_id) if file_id else None

        for asset_id, asset_name in project_files_ids.items():

            file_content = process_controller.get_file_content(file_id=asset_name)

            if not file_content:
                logger.error(f"Error while processing file: {asset_name}")
                if requested_asset_id is not None:
                    raise ProcessingError(f"Could not read file: {asset_name}")
                continue

            file_chunks = process_controller.process_file_content(
                file_content=file_content,
                file_id=asset_name,
                chunk_size=chunk_size,
                overlap_size=overlap_size
            )

            if not file_chunks:
                logger.error(f"No chunks for file_id: {asset_name}")
                if requested_asset_id is not None:
                    raise ProcessingError(f"No chunks for file: {asset_name}")
                continue

            file_chunks_records = [
                DataChunk(
                    chunk_text=chunk.page_content,
                    chunk_metadata=chunk.metadata,
                    chunk_order=i+1,
                    chunk_project_id=project.project_id,
                    chunk_asset_id=asset_id
                )
                for i, chunk in enumerate(file_chunks)
            ]

            # Replace, don't append: a retry (or a re-run) of the same file
            # must not duplicate its chunks. Only THIS file is touched.
            old_chunk_ids = await chunk_model.get_chunk_ids_by_asset_id(asset_id=asset_id)
            _ = await vectordb_client.delete_records_by_chunk_ids(
                collection_name=collection_name,
                chunk_ids=old_chunk_ids,
            )
            _ = await chunk_model.delete_chunks_by_asset_id(asset_id=asset_id)

            no_records += await chunk_model.insert_many_chunks(chunks=file_chunks_records)
            no_files += 1

        if no_files == 0:
            raise ProcessingError(f"No file could be processed for project_id: {project.project_id}")

        result = {
                    "signal": ResponseSignal.PROCESSING_SUCCESS.value,
                    "inserted_chunks": no_records,
                    "processed_files": no_files,
                    "project_id": project_id,
                    "do_reset": do_reset,
                    "card_id":card_id,
                    "file_id": requested_asset_id,
                }

        # store the FULL result, so a replay returns what the next task needs
        await idempotency_manager.update_task_status(
            execution_id=execution_id,
            status='SUCCESS',
            result=result
        )

        logger.warning(f"inserted_chunks: {no_records}")

        return result
    
    except TaskInProgress:
        raise
    except Exception as e:
        logger.error(f"Task failed: {str(e)}")
        if execution_id is not None:
            try:
                # so the retry can claim it immediately
                await idempotency_manager.update_task_status(
                    execution_id=execution_id,
                    status='FAILURE',
                    result={"error": str(e)[:500]}
                )
            except Exception as db_error:
                logger.error(f"Could not mark task as FAILURE: {str(db_error)}")
        raise
    finally:
        try:
            if db_engine:
                await db_engine.dispose()
            
            if vectordb_client:
                await vectordb_client.disconnect()
        except Exception as e:
            logger.error(f"Task failed while cleaning: {str(e)}")
