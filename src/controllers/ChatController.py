import asyncio

import logging

import re

from controllers.NLPController import NLPController

from controllers.VisionController import VisionController

from controllers.QuizController import QuizController
from models.AssetModel import AssetModel
from models.enums.AssetTypeEnum import AssetTypeEnum

logger = logging.getLogger("uvicorn.error")

OUT_OF_SCOPE_AR = (

    "انا منصه STUDY GATE مساعد تعليمي ليك قولي تحب نبدا منين  "

    "أنا هنا لمساعدتك في فهم المحاضرات، وشرح المفاهيم العلمية، "

    "وتلخيص ملفات PDF، وشرح الصور التعليمية، وحل المسائل، "

    "وإنشاء أسئلة للمراجعة. سؤالك خارج نطاق المنصة التعليمية. "

    "اسألني عن موضوع دراسي وسأساعدك فيه."

    "انا ال برمجني المهندس نور ذكي طالب modern academy "

)

OUT_OF_SCOPE_EN = (

    "I'm STUDY GATE AI, the educational assistant . "

    "I can help you understand lectures, explain academic concepts, "

    "summarize PDFs, explain educational images, solve problems, "

    "and prepare revision questions. Your request is outside my "

    "educational scope. Ask me about a study topic and I'll help."

    "i created by nour zaki , student in modern academy "

)

ROUTER_UNCERTAIN_AR = (

    "أنا STUDY GATE AI، المساعد التعليمي داخل منصة STUDY GATE. "

    "مش قادر أحدد طلبك بدقة. وضّح سؤالك أو أعد صياغته، "

    "وسأساعدك في الموضوع الدراسي المناسب."

)

ROUTER_UNCERTAIN_EN = (

    "I'm STUDY GATE AI, the educational assistant for STUDY GATE. "

    "I couldn't confidently classify your request. Please rephrase "

    "your question or clarify the study topic you need help with."

)

NO_DOCUMENT_CONTEXT_AR = (

    "مش لاقي معلومات كفاية في الملفات المرفوعة للإجابة عن السؤال ده."

)

NO_DOCUMENT_CONTEXT_EN = (

    "I couldn't find enough relevant information in your uploaded "

    "study materials to answer this question."

)

NO_IMAGE_AR = (
    "مش لاقي صورة مرفوعة. ارفع صورة تعليمية عشان أقدر أساعدك في سؤالك."
)

NO_IMAGE_EN = (
    "I couldn't find an uploaded image. Please upload an educational image so I can help with your question."
)

NO_RESOURCES_AR = (
    "مش لاقي صورة ولا ملفات مرفوعة. ارفع صورة أو ملف PDF عشان أقدر أساعدك."
)

NO_RESOURCES_EN = (
    "I couldn't find an uploaded image or any documents. Please upload an image or a PDF so I can help."
)

RETRIEVAL_LIMIT = 3

MAX_CHUNK_CHARS = 800

MAX_HISTORY_MESSAGES = 10

ROUTER_HISTORY_MESSAGES = 5

ROUTER_PROMPT = """Classify the user's CURRENT request.

Return exactly one label:

STUDY, DOCS, IMAGE, BOTH, QUIZ, or OFF_TOPIC.

STUDY:

An educational or academic question that can be answered using

general knowledge, even if no study material was uploaded.

Examples: Explain machine learning, what is a stack, solve a math problem.

DOCS:

The user asks about their uploaded PDFs, lectures, notes, or course materials.

IMAGE:

The user asks about educational content in an uploaded image only.

BOTH:

The answer requires both an educational image and uploaded study documents.

QUIZ:

The user explicitly asks to create a quiz, exam, test,

or multiple-choice questions for practice.

Examples:

- "Make me a quiz from this lecture" -> QUIZ

- "اعملي امتحان على المحاضرة" -> QUIZ

- "اختبرني في Data Structures" -> QUIZ

- "اشرحلي السؤال التالت" -> STUDY or DOCS

OFF_TOPIC:

The request is unrelated to studying or education.

Examples: Recommend a car, identify a household fan model,

shopping recommendations, unrelated personal requests.

Examples in Egyptian Arabic:

- "أجيب عربية نوعها إيه؟" -> OFF_TOPIC

- "نوع المروحة اللي عندنا إيه؟" -> OFF_TOPIC

- "اشرحلي إزاي المروحة بتشتغل من ناحية الفيزياء" -> STUDY

- "اشرحلي المحاضرة اللي رفعتها" -> DOCS

- "اشرحلي الصورة اللي رفعتها" -> IMAGE

Important rules:

- Classify the user's intent, not merely the words in the question.

- Uploaded files do not make an unrelated question a DOCS request.

- An uploaded image does not automatically make a question an IMAGE request.

- A general academic question is STUDY, not OFF_TOPIC.


- Use conversation history only to understand references in the current question.

- If the request is clearly outside the educational scope, return OFF_TOPIC.

Image available: {image_status}

Conversation history:

{history}

Current question: {question}

Classification:"""

class ChatController:

    def __init__(

        self,

        db_client,

        vectordb_client,

        generation_client,

        embedding_client,

        template_parser,

    ):

        self.db_client = db_client
        self.nlp = NLPController(

            vectordb_client=vectordb_client,

            generation_client=generation_client,

            embedding_client=embedding_client,

            template_parser=template_parser,

        )

        self.generation_client = generation_client

        self.vision = VisionController()

        self.quiz = QuizController(

            db_client=db_client,

            vectordb_client=vectordb_client,

            generation_client=generation_client,

            embedding_client=embedding_client,

            template_parser=template_parser,

        )

    @staticmethod

    def _format_history(

        history: list,

        limit: int = MAX_HISTORY_MESSAGES,

    ) -> list:

        """Keep valid user/assistant messages in chronological order."""

        valid_messages = []

        for message in history or []:

            if not isinstance(message, dict):

                continue

            role = message.get("role")

            content = message.get("content")

            if role not in ("user", "assistant") or not isinstance(content, str):

                continue

            content = content.strip()

            if content:

                valid_messages.append({

                    "role": role,

                    "content": content,

                })

        return valid_messages[-limit:]

    def _extract_quiz_params(self, question: str) -> dict:

        """

        Extract quiz parameters from the user question.

        Falls back to safe defaults.

        """

        question_lower = question.lower()
        # ----- Number of questions -----
        question_count = 5  # default

        count_match = re.search(

            r"(?:اعملي|اعمل|اعمللي|اعمل لي|make|create|generate)?\s*"

            r"(?:quiz|امتحان|اختبار|أسئلة|اسئلة)?\s*"

            r"(?:من|of|about)?\s*"

            r"(\d+)\s*(?:سؤال|أسئلة|اسئلة|questions?|q)",

            question_lower,

        )

        if not count_match:

            count_match = re.search(r"(\d+)\s*(?:سؤال|أسئلة|اسئلة|questions?)", question_lower)

        if count_match:

            try:

                count = int(count_match.group(1))

                if 1 <= count <= 20:

                    question_count = count

            except ValueError:

                pass
        # ----- Difficulty -----
        difficulty = "medium"

        if re.search(r"\b(easy|سهل|سهلة|بسيط|بسيطة)\b", question_lower):

            difficulty = "easy"

        elif re.search(r"\b(hard|صعب|صعبة|advanced|متقدم)\b", question_lower):

            difficulty = "hard"
        # ----- Topic (very light extraction) -----
        topic = None

        topic_match = re.search(

            r"(?:في|عن|على|from|about|on)\s+([^\n\\?\\.،,]{3,60})",

            question,

            re.IGNORECASE,

        )

        if topic_match:

            topic = topic_match.group(1).strip()
        
                # ----- Source selection -----
        has_image_request = bool(
            re.search(
                r"\b(image|picture|photo|images|pictures|photos)\b"
                r"|صورة|الصورة|الصور",
                question_lower,
            )
        )

        has_pdf_request = bool(
            re.search(
                r"\b(pdf|document|documents|file|files)\b"
                r"|ملف|الملف|الملفات|المستند|المستندات",
                question_lower,
            )
        )

        has_both_request = bool(
            re.search(
                r"\b(both|all sources|image and pdf|pdf and image)\b"
                r"|الاتنين|كلاهما|المصدرين|الصورة والملف|الملف والصورة",
                question_lower,
            )
        )

        if has_both_request or (has_image_request and has_pdf_request):
            source = "both"
        elif has_image_request:
            source = "image"
        elif has_pdf_request:
            source = "pdf"
        else:
            source = "auto"

        return {

            "question_count": question_count,

            "difficulty": difficulty,

            "topic": topic,

            "source": source,


        }

    async def _route(

        self,

        question: str,

        history: list,

        has_image: bool,

    ) -> str:

        """Classify the request before choosing its answer source."""

        question_lower = question.lower().strip()

        quiz_keywords = [

            r"\b(quiz|امتحان|اختبار)\b",

            r"(اعمل|اعملي|اعمللي|اعمل لي|اصنع|ولد|generate|create|make).{0,30}(quiz|امتحان|اختبار|mcq)",

            r"(اختبرني|اختبرنى)",

            r"(أسئلة|اسئلة|أسئله)\s+(مراجعة|quiz)",

            r"\bmcq\b",

        ]

        for pattern in quiz_keywords:

            if re.search(pattern, question_lower, re.IGNORECASE):

                logger.info("Chat router selected: QUIZ (rule-based)")

                return "QUIZ"
        # -------------------------------------------------        # 2. LLM Router (for the rest)        # -------------------------------------------------
        recent_history = self._format_history(

            history,

            limit=ROUTER_HISTORY_MESSAGES,

        )

        history_text = "\n".join(

            f"{item['role']}: {item['content'][:160]}"

            for item in recent_history

        ) or "No previous messages."

        prompt = ROUTER_PROMPT.format(

            image_status="yes" if has_image else "no",

            history=history_text,

            question=question,

        )

        try:

            output = await asyncio.to_thread(

                self.generation_client.generate_text,

                prompt=prompt,

                chat_history=[],

                temperature=0.1,

                max_output_tokens=16,

            )

            match = re.search(

                r"\b(OFF_TOPIC|STUDY|DOCS|IMAGE|BOTH|QUIZ)\b",

                (output or "").strip().upper(),

            )

            if match:
                route = match.group(1)
                logger.info("Chat router selected: %s", route)
                return route

            logger.warning("Unrecognized router output: %r", output)

        except Exception:

            logger.exception("Chat router failed.")

        return self._fallback_route(question, has_image)

    @staticmethod
    def _fallback_route(question: str, has_image: bool) -> str:
        lower = question.lower()

        wants_both = any(
            token in lower
            for token in (
                "both",
                "الاتنين",
                "الاتنين مع بعض",
                "الصورة والملف",
                "الصوره والملف",
            )
        )
        wants_image = any(
            token in lower
            for token in (
                "image",
                "photo",
                "picture",
                "الصورة",
                "الصوره",
                "الصور",
                "السبورة",
                "السبوره",
            )
        )
        wants_docs = any(
            token in lower
            for token in (
                "pdf",
                "document",
                "lecture",
                "notes",
                "الملف",
                "المحاضرة",
                "المحاضره",
                "المذكرة",
                "المذكره",
            )
        )

        if wants_both or (wants_image and wants_docs):
            return "BOTH"
        if wants_image:
            return "IMAGE"
        if wants_docs:
            return "DOCS"

        return "UNCERTAIN"

    async def _retrieve_context(

        self,

        project,

        question: str,

    ) -> str:

        try:

            documents = await self.nlp.search_vector_db_collection(

                project=project,

                text=question,

                limit=RETRIEVAL_LIMIT * 2,

            )

        except Exception:

            logger.exception("Chat RAG retrieval failed.")

            return ""

        if not isinstance(documents, list) or not documents:

            logger.info("No RAG documents retrieved.")

            return ""

        parts = []

        seen_texts = set()

        for document in documents:

            content = getattr(document, "text", "")

            if not isinstance(content, str) or not content.strip():

                continue

            score = getattr(document, "score", None)

            if score is not None and score < 0.35:

                continue

            normalized_text = " ".join(content.strip().split()).casefold()

            if normalized_text in seen_texts:

                continue

            seen_texts.add(normalized_text)

            chunk_text = self.generation_client.process_text(

                content.strip()[:MAX_CHUNK_CHARS]

            )

            document_prompt = self.nlp.template_parser.get(

                "rag",

                "document_prompt",

                {

                    "doc_num": len(parts) + 1,

                    "chunk_text": chunk_text,

                },

            )

            parts.append(document_prompt)

            if len(parts) >= RETRIEVAL_LIMIT:

                break

        return "\n\n".join(parts)


    def _is_arabic(self, text: str) -> bool:
      return bool(re.search(r"[\u0600-\u06FF]", text))

    async def answer(

        self,

        project,

        question: str,

        history: list,

        image: dict | None = None,

    ) -> str | dict:

        question = question.strip()

        if not question:

            raise ValueError("CHAT_EMPTY_QUESTION")

        history = self._format_history(history)

        route = await self._route(

            question=question,

            history=history,

            has_image=bool(image and image.get("image_data")),

        )
        # Classification failure
        if route == "UNCERTAIN":

            if re.search(r"[\u0600-\u06FF]", question):

                return ROUTER_UNCERTAIN_AR

            return ROUTER_UNCERTAIN_EN
        # Out of scope
        if route == "OFF_TOPIC":

            if re.search(r"[\u0600-\u06FF]", question):

                return OUT_OF_SCOPE_AR

            return OUT_OF_SCOPE_EN
        # ---------- QUIZ path ----------
        if route == "QUIZ":
            params = self._extract_quiz_params(question)
            source = params["source"]

            has_image = bool(image and image.get("image_data"))

            asset_model = await AssetModel.create_instance(
                db_client=self.db_client
            )
            uploaded_files = await asset_model.get_all_project_assets(
                asset_project_id=project.project_id,
                asset_type=AssetTypeEnum.FILE.value,
            )
            has_documents = bool(uploaded_files)

            # Explicit source checks
            if source == "pdf" and not has_documents:
                return (
                    "مفيش ملفات مرفوعة للمشروع. ارفع ملف PDF."
                    if self._is_arabic(question)
                    else "No documents uploaded. Please upload a PDF."
                )

            if source == "image" and not has_image:
                return NO_IMAGE_AR if self._is_arabic(question) else NO_IMAGE_EN

            # Both / auto: use whichever source is available
            if source in ("both", "auto") and not has_image and not has_documents:
                return (
                    NO_RESOURCES_AR
                    if self._is_arabic(question)
                    else NO_RESOURCES_EN
                )

            # Decide whether document retrieval is allowed
            use_documents = (
                source in ("pdf", "both", "auto")
                and has_documents
            )

            # Extract image content only when the selected source allows it
            image_text = None
            use_image = source in ("image", "both", "auto") and has_image

            if use_image:
                image_text = await self.vision.analyze_image(
                    image["image_data"]
                )

            try:
                quiz = await self.quiz.generate_quiz(
                    project=project,
                    question_count=params["question_count"],
                    difficulty=params["difficulty"],
                    topic=params["topic"],
                    source_text=image_text,
                    use_documents=use_documents,
                )
            except LookupError:
                # The PDF may be uploaded but not indexed, or contain
                # insufficient retrievable study material.
                if source == "pdf":
                    return (
                        NO_DOCUMENT_CONTEXT_AR
                        if self._is_arabic(question)
                        else NO_DOCUMENT_CONTEXT_EN
                    )

                # For both/auto, image content may still be usable,
                # but generation failed because the available material
                # was insufficient.
                if source in ("both", "auto") and use_image and not use_documents:
                    return (
                        NO_DOCUMENT_CONTEXT_AR
                        if self._is_arabic(question)
                        else NO_DOCUMENT_CONTEXT_EN
                    )

                raise

            return {
                "type": "quiz",
                "quiz_id": quiz["quiz_id"],
                "question_count": quiz["question_count"],
                "questions": quiz["questions"],
            }

        # ---------- Detect available resources ----------
        has_image = bool(image and image.get("image_data"))

        asset_model = await AssetModel.create_instance(
            db_client=self.db_client
        )
        uploaded_files = await asset_model.get_all_project_assets(
            asset_project_id=project.project_id,
            asset_type=AssetTypeEnum.FILE.value,
        )
        has_documents = bool(uploaded_files)

        # If STUDY was selected, use general knowledge only when
        if route == "STUDY":
            if has_documents:
                route = "DOCS"
            elif has_image:
                route = "IMAGE"

        # Use an available source when the requested source is missing.
        if route == "BOTH":
            if not has_documents and not has_image:
                return (
                    NO_RESOURCES_AR
                    if self._is_arabic(question)
                    else NO_RESOURCES_EN
                )
            elif not has_documents:
                route = "IMAGE"
            elif not has_image:
                route = "DOCS"

        elif route == "DOCS" and not has_documents:
            if has_image:
                route = "IMAGE"
            else:
                return (
                    "مفيش ملفات مرفوعة للمشروع. ارفع ملف PDF."
                    if self._is_arabic(question)
                    else "No documents uploaded. Please upload a PDF."
                )

        elif route == "IMAGE" and not has_image:
            if has_documents:
                route = "DOCS"
            else:
                return (
                    NO_IMAGE_AR
                    if self._is_arabic(question)
                    else NO_IMAGE_EN
                )

        needs_image = route in ("IMAGE", "BOTH")
        needs_docs = route in ("DOCS", "BOTH")
        # Retrieve context only when needed
        context = ""

        if route in ("DOCS", "BOTH"):

            context = await self._retrieve_context(

                project=project,

                question=question,

            )
        # No relevant documents found
        if route == "DOCS" and not context.strip():
            if re.search(r"[\u0600-\u06FF]", question):

                return NO_DOCUMENT_CONTEXT_AR

            return NO_DOCUMENT_CONTEXT_EN

        footer_prompt = ""

        if route in ("DOCS", "BOTH") and context:

            footer_prompt = self.nlp.template_parser.get(

                "rag",

                "footer_prompt",

                {"query": question},

            )
        # Image paths
        if image and image.get("image_data") and route in ("IMAGE", "BOTH"):

            description = image.get("description") or ""

            return await self.vision.answer_question(

                image_bytes=image["image_data"],

                image_description=description,

                history=history,

                question=question,

                documents_context=context if route == "BOTH" else "",

            )
        # Text / STUDY / DOCS path
        base_system_prompt = self.nlp.template_parser.get("rag", "system_prompt")

        system_content = (

            f"{base_system_prompt}\n\n"

           "## Unified Chat Instructions (CRITICAL)\n"

            "- You are STUDY GATE AI, an educational assistant. Your only job is to help with studying.\n"

            "- Answer the current question directly and helpfully.\n"

            "- Never refuse a legitimate educational, academic, or study-related question.\n"

            "- Use conversation history only to understand follow-ups and references.\n"

            "- If uploaded pdf/files/documents/photo are provided, answer ONLY from the information in those documents/pdf / photo.\n"

            "- If no files/documents are uploaded, answer general educational or scientific questions using your knowledge (e.g. \"explain machine learning ...\").\n"

            "- Do not invent that information came from documents if it is not in the context.\n"

            "- Keep answers clear, structured, and focused on the student's question.\n\n"

            "## Relevant project documents\n"

            f"{context or 'No relevant project documents were retrieved.'}"

        )

        system_message = {

            "role": "system",

            "content": system_content,

        }

        prompt = (

            f"{footer_prompt}\n\n## Relevant Document Context\n{context}"

            if footer_prompt and context

            else question

        )
        # First attempt
        answer = await asyncio.to_thread(

            self.generation_client.generate_text,

            prompt=prompt,

            chat_history=[system_message] + history,

        )
        # ---- Refusal detection + one retry ----
        REFUSAL_PATTERNS = [

            r"i'?m sorry.? but i can'?t assist",

            r"i cannot assist",

            r"i can'?t help with that",

            r"i'?m unable to (help|assist|answer)",

            r"sorry.? i can'?t",

            r"as an ai.? i (cannot|can'?t)",

            r"i must decline",

            r"outside (of )?my (scope|guidelines)",

        ]

        def is_refusal(text: str) -> bool:

            if not isinstance(text, str) or not text.strip():

                return True

            lower = text.strip().lower()

            return any(re.search(p, lower) for p in REFUSAL_PATTERNS)

        if is_refusal(answer):

            logger.warning("Model refused educational request. Retrying with stronger instruction.")

            retry_system = {

                "role": "system",

                "content": (

                    system_content

                    + "\n\n## RETRY INSTRUCTION (VERY IMPORTANT)\n"

                    "The previous response was a refusal. This is an educational platform. "

                    "You MUST answer the student's academic/study question helpfully. "

                    "Do not refuse. Provide a clear, useful educational answer."

                ),

            }

            answer = await asyncio.to_thread(

                self.generation_client.generate_text,

                prompt=prompt,

                chat_history=[retry_system] + history,

            )
        # Final fallback if still refusing
        if is_refusal(answer):

            logger.error("Model refused after retry. Returning safe educational fallback.")

            if re.search(r"[\u0600-\u06FF]", question):

                return (

                    "أنا STUDY GATE AI. ممكن توضح سؤالك الدراسي أكتر؟ "

                    "مثلاً: اشرحلي المفهوم ده، حل المسألة دي، أو لخص الجزء ده من المحاضرة."

                )

            return (

                "I'm STUDY GATE AI. Could you rephrase your study question? "

                "For example: explain this concept, solve this problem, or summarize this lecture part."

            )

        if not isinstance(answer, str) or not answer.strip():

            raise ValueError("CHAT_EMPTY_RESPONSE")

        return answer.strip()
