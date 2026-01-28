from enum import Enum

class ResponseSignal(Enum):
    FILE_TYPE_NOT_SUPPORTED = "file_type_not_supported"
    FILE_SIZE_EXCEEDED      = "file_size_exceeded"
    FILE_UPLOADED_SUCCESS   = "file_upload_successfully"
    FILE_UPLOADED_FAILED    = "file_upload_failed"
    FILE_VALIDATED_SUCCESS  = "file_validated_successfully"
    