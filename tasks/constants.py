class HTTPStatusMessage:
    FILE_UPLOADED_SUCCESSFULLY: str = "File uploaded successfully"
    FILE_NOT_FOUND: str = "File not found"
    CAN_NOT_LOAD_FILE: str = "Can Not Load the File"
    CAN_NOT_CHUNK_FILE: str = "Can Not Chunk the File"
    CAN_NOT_SAVE_CHUNKS_TO_DB: str = "Can Not Save Chunks to Database"
    FILE_INDEXED_SUCCESSFULLY: str = "File indexed successfully"
    SEARCH_SUCCESSFULLY: str = "Search successfully"
    NO_RELATED_DOCUMENTS_FOUND: str = "No related documents found"
    LLM_ANSWER_RETURNED_SUCCESSFULLY: str = "LLM answer returned successfully"

class TaskConstants:
    CSV = 'csv'
    PDF = 'pdf'
    JSONL = 'jsonl'
    TXT = 'txt'