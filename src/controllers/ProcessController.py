from .BaseController import BaseController
from .ProjectController import ProjectController
import os
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import PyMuPDFLoader
from models import ProcessingEnum
from typing import List
from dataclasses import dataclass
import re



_REF_HEADING_RE = re.compile(
    r"^\s*(?:references?|bibliography|works\s+cited|المراجع|المصادر)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

@dataclass
class Document:
    page_content: str
    metadata: dict

class ProcessController(BaseController):

    def __init__(self, project_id: str):
        super().__init__()

        self.project_id = project_id
        self.project_path = ProjectController().get_project_path(project_id=project_id)

    def get_file_extension(self, file_id: str):
        return os.path.splitext(file_id)[-1]

    def get_file_loader(self, file_id: str):

        file_ext = self.get_file_extension(file_id=file_id)
        file_path = os.path.join(
            self.project_path,
            file_id
        )

        if not os.path.exists(file_path):
            return None

        if file_ext == ProcessingEnum.TXT.value:
            return TextLoader(file_path, encoding="utf-8")

        if file_ext == ProcessingEnum.PDF.value:
            return PyMuPDFLoader(file_path)
        
        return None

    def get_file_content(self, file_id: str):

        loader = self.get_file_loader(file_id=file_id)
        if loader:
            return loader.load()

        return None



    @staticmethod
    def _strip_references(text: str) -> str:
     """Cut everything after the last 'References' heading (only if it's in the last 40% of the doc)."""
     matches = list(_REF_HEADING_RE.finditer(text))
     if not matches:
         return text
     last = matches[-1]
     if last.start() >= len(text) * 0.6:
        return text[:last.start()]
     return text

    def process_file_content(self, file_content: list, file_id: str,
                        chunk_size: int = 1000, overlap_size: int = 20):
     texts = [rec.page_content for rec in file_content]
     metadatas = [rec.metadata for rec in file_content]
     return self.process_simpler_splitter(
         texts=texts, metadatas=metadatas,
         chunk_size=chunk_size, overlap_size=overlap_size,
     )

    def process_simpler_splitter(self, texts: List[str], metadatas: List[dict],
                              chunk_size: int, splitter_tag: str = "\n",
                              overlap_size: int = 0):
     full_text = "\n".join(texts)
     full_text = self._strip_references(full_text)

     paragraphs = [
         re.sub(r"\s+", " ", p).strip()
         for p in re.split(r"\n\s*\n", full_text)
     ]
     paragraphs = [p for p in paragraphs if len(p) > 1]

     if len(paragraphs) <= 1:
        paragraphs = [
            re.sub(r"\s+", " ", l).strip()
            for l in full_text.split(splitter_tag) if len(l.strip()) > 1
        ]

     chunks, current = [], ""
     for para in paragraphs:
        if current and len(current) + len(para) + 1 > chunk_size:
            chunks.append(current.strip())
            tail = current[-overlap_size:] if overlap_size else ""
            current = tail
        current += (" " if current else "") + para
        # فقرة أطول من الحد: قسّمها
        while len(current) > chunk_size * 2:
            chunks.append(current[:chunk_size].strip())
            current = current[chunk_size - overlap_size:]

     if current.strip():
        chunks.append(current.strip())

     return [Document(page_content=c, metadata={}) for c in chunks]


    

