
from .BaseController import BaseController
from models.db_schemes import Project, DataChunk
from stores.llm.LLMEnums import DocumentTypeEnum
from typing import List
import json


class NLPController(BaseController):
    def __init__(
        self,
        vectordb_client,
        generation_client,
        embedding_client,
        template_parser
    ):
        super().__init__()
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.template_parser = template_parser

    def create_collection_name(self, project_id: str):
        return f"collection_{self.vectordb_client.default_vector_size}_{project_id}".strip()

    async def reset_vector_db_collection(self, project: Project):
        collection_name = self.create_collection_name(
            project_id=project.project_id
        )
        return await self.vectordb_client.delete_collection(
            collection_name=collection_name
        )

    async def get_vector_db_collection_info(self, project: Project):
        collection_name = self.create_collection_name(
            project_id=project.project_id
        )
        collection_info = await self.vectordb_client.get_collection_info(
            collection_name=collection_name
        )
        return json.loads(
            json.dumps(collection_info, default=lambda x: x.__dict__)
        )

    async def index_into_vector_db(
        self,
        project: Project,
        chunks: List[DataChunk],
        chunks_ids: List[int],
        do_reset: bool = False
    ):
        collection_name = self.create_collection_name(
            project_id=project.project_id
        )

        texts = [chunk.chunk_text for chunk in chunks]
        metadata = [chunk.chunk_metadata for chunk in chunks]

        vectors = self.embedding_client.embed_text(
            text=texts,
            document_type=DocumentTypeEnum.DOCUMENT.value
        )

        await self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.embedding_client.embedding_size,
            do_reset=do_reset,
        )

        await self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts,
            metadata=metadata,
            vectors=vectors,
            record_ids=chunks_ids,
        )

        return True

    async def search_vector_db_collection(
        self,
        project: Project,
        text: str,
        limit: int = 10
    ):
        collection_name = self.create_collection_name(
            project_id=project.project_id
        )

        vectors = self.embedding_client.embed_text(
            text=text,
            document_type=DocumentTypeEnum.QUERY.value
        )

        if not vectors:
            return []

        query_vector = vectors[0]

        if query_vector is None:
            return []

        results = await self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            vector=query_vector,
            limit=limit
        )

        return results if isinstance(results, list) else []

    async def answer_rag_question(
        self,
        project: Project,
        query: str,
        limit: int = 6
    ):
        answer, full_prompt, chat_history = None, None, None

        retrieval_limit = max(limit * 2, limit)

        retrieved_documents = await self.search_vector_db_collection(
            project=project,
            text=query,
            limit=retrieval_limit,
        )

        if not retrieved_documents:
            return answer, full_prompt, chat_history

        unique_documents = []
        seen_texts = set()

        for doc in retrieved_documents:
            if not doc.text or not doc.text.strip():
                continue

            if (
                hasattr(doc, "score")
                and doc.score is not None
                and doc.score < 0.35
            ):
                continue

            normalized_text = " ".join(
                doc.text.strip().split()
            ).casefold()

            if normalized_text in seen_texts:
                continue

            seen_texts.add(normalized_text)
            unique_documents.append(doc)

            if len(unique_documents) >= limit:
                break

        retrieved_documents = unique_documents

        if not retrieved_documents:
            return answer, full_prompt, chat_history

        system_prompt = self.template_parser.get(
            "rag",
            "system_prompt"
        )

        documents_prompts = "\n".join([
            self.template_parser.get(
                "rag",
                "document_prompt",
                {
                    "doc_num": idx + 1,
                    "chunk_text": self.generation_client.process_text(
                        doc.text
                    ),
                }
            )
            for idx, doc in enumerate(retrieved_documents)
        ])

        footer_prompt = self.template_parser.get(
            "rag",
            "footer_prompt",
            {"query": query}
        )

        chat_history = [
            self.generation_client.construct_prompt(
                prompt=system_prompt,
                role=self.generation_client.enums.SYSTEM.value,
            )
        ]

        full_prompt = "\n\n".join([
            documents_prompts,
            footer_prompt
        ])

        answer = self.generation_client.generate_text(
            prompt=full_prompt,
            chat_history=chat_history
        )

        return answer, full_prompt, chat_history
