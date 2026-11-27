from celery_app import celery_app, get_setup_utils
from helpers.config import get_settings
import asyncio
from fastapi.responses import JSONResponse
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from controllers import NLPController
from models import ResponseSignal
from tqdm.auto import tqdm

import logging
logger = logging.getLogger(__name__)



class IndexingError(Exception):
    """Permanent failure: retrying will not help."""

@celery_app.task(
    bind=True, name="tasks.data_indexing.index_data_content",
    autoretry_for=(Exception,),
    dont_autoretry_for=(ValueError, LookupError, IndexingError),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)

def index_data_content(self, project_id: int, do_reset: int,card_id=None, file_id=None):

    logger.warning("index_data_content started")
    return asyncio.run(
        _index_data_content(self, project_id, do_reset,card_id, file_id)
    )

async def _index_data_content(task_instance, project_id: int, do_reset: int ,card_id=None, file_id=None):

    db_engine, vectordb_client = None, None

    try:

        if card_id is None or file_id is None:
            raise ValueError("card_id and file_id are required for indexing")

        (db_engine, db_client, llm_provider_factory,vectordb_provider_factory,
        generation_client, embedding_client,
        vectordb_client, template_parser) = await get_setup_utils()

        logger.warning("Setup utils were loaded!")

        project_model = await ProjectModel.create_instance(
            db_client=db_client
        )

        chunk_model = await ChunkModel.create_instance(
            db_client=db_client
        )

        project = await project_model.get_project_by_id(
            project_id=project_id
        )

        if project is None:
            task_instance.update_state(
                state="FAILURE",
                meta={
                    "signal": ResponseSignal.PROJECT_NOT_FOUND_ERROR.value
                },
            )
            raise LookupError(
                f"No project found for project_id: {project_id}"
            )
    
        nlp_controller = NLPController(
            vectordb_client=vectordb_client,
            generation_client=generation_client,
            embedding_client=embedding_client,
            template_parser=template_parser,
        )

        has_records = True
        page_no = 1
        inserted_items_count = 0

        collection_name = nlp_controller.create_collection_name(project_id=project.project_id)

        await vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=embedding_client.embedding_size,
            do_reset=False,
        )

        if do_reset:
            file_chunk_ids = await chunk_model.get_chunk_ids_by_asset_id(asset_id=file_id)
            deleted_count = await vectordb_client.delete_records_by_chunk_ids(
                collection_name=collection_name,
                chunk_ids=file_chunk_ids,
            )
            logger.warning(
                f"do_reset: removed {deleted_count} vectors | "
                f"file_id: {file_id} | project_id: {project_id}"
            )
            
        total_chunks_count = await chunk_model.get_chunks_count_by_asset_id(asset_id=file_id)

        while True:
            if file_id is not None:
                page_chunks = await chunk_model.get_chunks_by_asset_id(
                    asset_id=file_id, page_no=page_no
                )
            else:
                page_chunks = await chunk_model.get_poject_chunks(
                    project_id=project.project_id, page_no=page_no
                )

            if not page_chunks:
                break
            page_no += 1

            chunks_ids = [c.chunk_id for c in page_chunks]

            is_inserted = await nlp_controller.index_into_vector_db(
                project=project,
                chunks=page_chunks,
                chunks_ids=chunks_ids,
                card_id=card_id,
            )

            if not is_inserted:
                task_instance.update_state(
                    state="FAILURE",
                    meta={"signal": ResponseSignal.INSERT_INTO_VECTORDB_ERROR.value},
                )
                raise Exception(f"can not insert into vectorDB | project_id: {project_id}")

            inserted_items_count += len(page_chunks)

        if inserted_items_count == 0 or inserted_items_count < (total_chunks_count or 0):
            task_instance.update_state(
                state="FAILURE",
                meta={"signal": ResponseSignal.INSERT_INTO_VECTORDB_ERROR.value},
            )
            raise IndexingError(
                f"indexed {inserted_items_count}/{total_chunks_count} chunks "
                f"| project_id: {project_id} | file_id: {file_id}"
            )

        return {
            "signal": ResponseSignal.INSERT_INTO_VECTORDB_SUCCESS.value,
            "inserted_items_count": inserted_items_count,
        }

    except Exception as e:
        logger.error(f"Task failed: {str(e)}")
        raise
    finally:
        try:
            if db_engine:
                await db_engine.dispose()

            if vectordb_client:
                await vectordb_client.disconnect()
        except Exception as e:
            logger.error(f"Task failed while cleaning: {str(e)}")