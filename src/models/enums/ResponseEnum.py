from enum import Enum

class ResponseEnum(Enum):

    FILE_VALIDATED_SUCCESS = 'file_validate_successfully'
    FILE_UPLOAD_SUCCESS = 'file_uploaded_successfully'
    FILE_UPLOAD_FAIL = 'file_upload_failed'
    FILE_TYPE_NOT_SUPPORTED = 'file_type_not_supported'
    FILE_SIZE_EXCEED = 'file_size_exceeded'
    PROCESSING_FAIL = 'file_processing_failed'
    PROCESSING_SUCCESS = 'file_processing_success'
    NO_FILE_ERROR = 'not_found_files'
    FILE_ID_ERROR = 'no_file_found_with_this_id'
    PROJECT_NOT_FOUND = 'project_not_found'
    INSERT_INTO_VECTORDB_ERROR = 'insert_into_vectordb_error'
    INSERT_INTO_VECTORDB_SUCCESS = 'insert_into_vectordb_success'
    VECTORDB_COLLECTION_RETRIEVED = 'vectordb_collection_retrieved'
    VECTORDB_SEARCH_ERROR = 'vectordb_search_error'
    VECTORDB_SEARCH_SUCCESS = 'vectordb_search_success'
    RAG_ANSWER_ERROR = 'rag_answer_error'
    RAG_ANSWER_SUCCESS = 'rag_answer_success'