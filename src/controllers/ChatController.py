import asyncio
import logging
import re
from controllers.NLPController import NLPController
from controllers.VisionController import VisionController
from controllers.QuizController import QuizController
from models.AssetModel import AssetModel
from models.enums.AssetTypeEnum import AssetTypeEnum
from models.ChunkModel import ChunkModel
import os
import json

NO_DOCUMENT_CONTEXT_AR = (
    "مش لاقي المعلومة دي في الملفات المرفوعة. "
    "لو حابب أجاوب من معرفتي العامة قولي."
)

NO_DOCUMENT_CONTEXT_EN = (
    "I couldn't find this information in your uploaded materials. "
    "If you want me to answer from general knowledge, just tell me."
)

QUIZ_OFFER_NO_FILES_AR = (
    "مفيش ملفات أو صور مرفوعة للكارت ده. أقدر أعملك كويز من معرفتي العامة، "
    "اكتبلي الموضوع كده: اعملي كويز عن [الموضوع]."
)
QUIZ_OFFER_NO_FILES_EN = (
    "There are no uploaded files or images for this card. I can create a quiz from "
    "my general knowledge. Tell me the topic, e.g.: make a quiz about [topic]."
)
QUIZ_ASK_TOPIC_AR = "تحب الكويز يبقى عن أنهي موضوع؟ مثلًا: اعملي كويز عن Data Structures من معرفتك."
QUIZ_ASK_TOPIC_EN = "Which topic should the quiz cover? For example: make a quiz about Data Structures from your knowledge."
QUIZ_NOT_READY_AR = (
    "ملفات الكارت لسه مش جاهزة (يمكن بتتعالج أو مفيهاش نص). "
    "جرّب كمان شوية، أو اكتب: اعملي كويز عن [الموضوع] من معرفتك."
)
QUIZ_NOT_READY_EN = (
    "This card's files aren't ready yet (still processing, or no readable text). "
    "Try again shortly, or write: make a quiz about [topic] from your knowledge."
)

SUMMARY_GROUP_CHARS = 12000
SUMMARY_MAX_CHARS = 60000

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

    "I'm STUDY GATE AI, the educational assistant. "

    "I couldn't confidently classify your request. Please rephrase "

    "your question or clarify the study topic you need help with."

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

- "explain the PDF" -> DOCS
- "explain content " -> BOTH
- "summarize the uploaded file" -> DOCS
- "اشرحلي الـ PDF" -> DOCS

- "explain the image" -> IMAGE
- "summarize the text in this image" -> IMAGE
- "اشرحلي الصورة" -> IMAGE

- "اشرحلي الـ PDF" → DOCS (حتى لو السؤال عام، المقصود المحتوى المرفوع)
- "explain the PDF" → DOCS
- "لخص الملف" → DOCS
- "اشرحلي المحاضرة" → DOCS

- "Make me a quiz from this lecture" -> QUIZ

- "اعملي امتحان على المحاضرة" -> QUIZ

- "اختبرني في Data Structures" -> QUIZ

- "اشرحلي السؤال التالت" -> DOCS

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

Documents available: {document_status}

Image available: {image_status}

- If no documents are available, never return DOCS or BOTH.

- If no image is available, never return IMAGE or BOTH.

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
    def _wants_general_knowledge(self, question: str) -> bool:
        """Return True only if the user explicitly asks to answer without the uploaded files."""
        q = question.lower().strip()

        patterns = [
        # Arabic
        r"(من غير|بدون|من غير ما|من غير استخدام|من غير الاعتماد على).{0,35}(الملف|الملفات|المحاضرة|المحاضره|الـ\s*pdf|الpdf|pdf|المستندات)",
        r"(جاوب|جاوبني|رد|اشرح|قولي).{0,25}(من معرفتك|من معلوماتك|من غير الملفات|بدون الملفات|معرفة عامة|معلومات عامة)",
        r"(متستخدمش|متعتمدش على|تجاهل).{0,20}(الملف|الملفات|المحاضرة|pdf)",
        
        # English
         r"(answer|explain|reply|tell me).{0,30}(from your knowledge|using your knowledge|without the files|without the pdf|without documents|general knowledge)",
         r"(ignore|don't use|do not use).{0,20}(the file|the files|the pdf|documents|uploaded)",
                      ]

        return any(re.search(p, q, re.IGNORECASE) for p in patterns)

    @staticmethod
    def _clean_topic(topic: str | None) -> str | None:
        """Drop trailing noise like 'من معرفتك' or '5 اسئلة' that the topic regex captures."""
        if not topic:
            return None
        cleaned = re.sub(
            r"\s*(من\s+(معرفتك|معلوماتك|عندك)"
            r"|(بدون|من\s+غير|من\s+دون)\s+(الملفات|الملف|ملفات|pdf)"
            r"|from\s+(your\s+)?(general\s+)?knowledge"
            r"|without\s+(the\s+)?(files?|pdf)"
            r"|\d+\s*(سؤال|أسئلة|اسئلة|questions?)).*$",
            "",
            topic,
            flags=re.IGNORECASE,
        ).strip()
        if cleaned and re.fullmatch(
            r"(your\s+|ur\s+)?(general\s+)?know\w*|(your\s+)?general",
            cleaned,
            re.IGNORECASE,
                  ):
          return None
        return cleaned or None

    def _wants_knowledge_quiz(self, question: str) -> bool:
        if self._wants_general_knowledge(question):
            return True
        return bool(
            re.search(
                r"من\s+(معرفتك|معلوماتك|عندك|النولدج)"
                r"|من\s+دون\s+(الملف|الملفات|ملفات|pdf)"
                r"|\b(from|using)\s+(your\s+)?(general\s+)?knowledge\b"
                r"|\bgeneral\s+knowledge\b",
                question.lower(),
            )
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

        GENERIC_TOPIC_WORDS = {
         "المحاضرة", "المحاضره", "الملف", "الملفات", "الصورة", "الصوره",
         "الصور", "المستند", "المستندات", "pdf", "the pdf", "lecture",
         "the lecture", "file", "the file", "image", "the image",
         "document", "documents",
               }

        TOPIC_PATTERN = re.compile(
          r"(?:(?<![\w])(?:في|عن|على)(?![\w])|\b(?:from|about|on)\b)"
          r"\s+([^\n?.،,]{3,60})",
          re.IGNORECASE,
             )

        topic = None
        for m in TOPIC_PATTERN.finditer(question):
            candidate = m.group(1).strip()
            if candidate.lower() not in GENERIC_TOPIC_WORDS:
                topic = candidate
                break
        has_image_request = bool(
            re.search(
                r"\b(image|picture|photo|img|images|pictures|photos|pic|pics)\b"
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
        has_documents: bool = False,

    ) -> str:

        """Classify the request before choosing its answer source."""

        question_lower = question.lower().strip()

        quiz_keywords = [

            r"(اعمل|اعملي|اعمللي|اعمل لي|اصنع|ولد|ولّد|generate|create|make).{0,30}(quiz|كويز|امتحان|اختبار|mcq)",
            r"(اختبرني|اختبرنى)",
            r"(أسئلة|اسئلة|أسئله)\s+(مراجعة|quiz)",
            r"\bmcq\b",
            r"\bquiz me\b",

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
            document_status="yes" if has_documents else "no",
            history=history_text,
            question=question,
        )

        

        try:

            output = await asyncio.to_thread(

                self.generation_client.generate_text,

                prompt=prompt,

                chat_history=[],

                temperature=0.1,

                max_output_tokens=64,

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
        card_id: int,
        min_score: float = 0.35

    )  -> tuple[str, list]:
        logger.info("RAG search: card_id=%s query=%r", card_id, question[:80])

        try:

            documents = await self.nlp.search_vector_db_collection(

                project=project,

                text=question,

                limit=RETRIEVAL_LIMIT * 2,
                card_id=card_id,


            )

        except Exception:

            logger.exception("Chat RAG retrieval failed.")

            return "", []            
        logger.info(
            "RAG retrieved %d docs for card_id=%s",
            len(documents) if isinstance(documents, list) else 0,
            card_id,
        )

        if not isinstance(documents, list) or not documents:

            logger.info("No RAG documents retrieved.")

            return "", []      

        parts = []
        metas = []

        seen_texts = set()

        for document in documents:

            content = getattr(document, "text", "")

            if not isinstance(content, str) or not content.strip():

                continue

            score = getattr(document, "score", None)

            if score is not None and score < min_score:

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
            metas.append(getattr(document, "metadata", None))
            if len(parts) >= RETRIEVAL_LIMIT:

                break

        return "\n\n".join(parts), self._build_sources(metas)

    def _is_arabic(self, text: str) -> bool:
      return bool(re.search(r"[\u0600-\u06FF]", text))
    
    @staticmethod
    def _detect_source(question: str) -> str:

     q = question.lower()
     image = re.search(r"\b(image|img|imgs|picture|photo|images|pictures|pic|pics|photos)\b|صورة|الصورة|الصور|الصوره", q)
     pdf = re.search(r"\b(pdf|document|documents|file|files|lecture)\b|ملف|الملف|الملفات|المستند|المحاضرة|المحاضره", q)
     both = re.search(r"\b(both|all sources)\b|الاتنين|كلاهما|المصدرين", q)

     if both or (image and pdf):
          return "both"
     if image:
          return "image"
     if pdf:
          return "pdf"
     return "auto"

    async def answer(

        self,
        card_id: int,
        project,

        question: str,

        history: list,

        image: dict | None = None,
        image_descriptions: str = "",
        on_token=None,

    ) -> str | dict:

        question = question.strip() 
        
        if not question:

            raise ValueError("CHAT_EMPTY_QUESTION")

        history = self._format_history(history)

        image_description=image_descriptions or (image or {}).get("description") or ""
        has_image = bool(image_descriptions) or bool(image and image.get("image_data"))

        asset_model = await AssetModel.create_instance(db_client=self.db_client)
        uploaded_files = await asset_model.get_all_project_assets(
            asset_project_id=project.project_id,
            asset_type=AssetTypeEnum.FILE.value,
            card_id=card_id,
        )
        has_documents = bool(uploaded_files)

        route = await self._route(
            question=question,
            history=history,
            has_image=has_image,
            has_documents=has_documents,
        )
        
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
            is_ar = self._is_arabic(question)
            params = self._extract_quiz_params(question)
            source = params["source"]
            topic = self._clean_topic(params["topic"])

            if self._wants_knowledge_quiz(question):
                source = "none"

            if source == "pdf" and not has_documents:
                return (
                    "مفيش ملفات مرفوعة للمشروع. ارفع ملف PDF."
                    if is_ar
                    else "No documents uploaded. Please upload a PDF."
                )

            if source == "image" and not has_image:
                return NO_IMAGE_AR if is_ar else NO_IMAGE_EN

            if source == "both" and not has_image and not has_documents:
                return NO_RESOURCES_AR if is_ar else NO_RESOURCES_EN

            # No material to draw from (or the user asked for general knowledge)
            if source == "none" or (
                source == "auto" and not has_documents and not has_image
            ):
                if not topic:
                    if source == "auto":
                        return QUIZ_OFFER_NO_FILES_AR if is_ar else QUIZ_OFFER_NO_FILES_EN
                    return QUIZ_ASK_TOPIC_AR if is_ar else QUIZ_ASK_TOPIC_EN
                return await self.quiz.generate_knowledge_quiz(
                    project=project,
                    card_id=card_id,
                    topic=topic,
                    question_count=params["question_count"],
                    difficulty=params["difficulty"],
                    language="Arabic" if is_ar else "English",
                )

            use_documents = source in ("pdf", "both", "auto") and has_documents
            use_image = source in ("image", "both", "auto") and has_image
            image_text = None
            if use_image:
                image_text = image_descriptions or (image or {}).get("description") or None

            try:
                return await self.quiz.generate_quiz(
                    project=project,
                    question_count=params["question_count"],
                    difficulty=params["difficulty"],
                    topic=topic,
                    source_text=image_text,
                    use_documents=use_documents,
                    card_id=card_id,
                )
            except LookupError:
                if use_documents:
                    return QUIZ_NOT_READY_AR if is_ar else QUIZ_NOT_READY_EN
                if use_image or source == "image":
                    return NO_IMAGE_AR if is_ar else NO_IMAGE_EN
                return NO_RESOURCES_AR if is_ar else NO_RESOURCES_EN

        # If STUDY was selected, use general knowledge only when
      #  if route == "STUDY":
       #  if has_documents and has_image:
        #   route = "BOTH"
        # elif has_documents:
         #  route = "DOCS"
         #elif has_image:
         # route = "IMAGE"


        # If STUDY was selected:
        general_only = self._wants_general_knowledge(question)
        if general_only:
          if route == "DOCS":
           route = "STUDY"
          elif route == "BOTH":
           route = "IMAGE" if has_image else "STUDY" 


        src = self._detect_source(question)

        if route == "BOTH" and src == "image" and has_image:
            route = "IMAGE"            
        elif route == "BOTH" and src == "pdf" and has_documents:
            route = "DOCS"           

            
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
        sources = []

        if route in ("DOCS", "BOTH") or (
            route == "STUDY" and has_documents and not general_only
        ):

          context , sources= await self._retrieve_context(
                project=project,
                question=self._build_search_query(question, history),
                card_id=card_id,
            )
 
 
        # No relevant documents found (DOCS and BOTH)
        if route == "BOTH" and not context.strip():
  
            return (
                NO_DOCUMENT_CONTEXT_AR
                if self._is_arabic(question)
                else NO_DOCUMENT_CONTEXT_EN
            )

        if route == "DOCS" and not context.strip():
            return (
                NO_DOCUMENT_CONTEXT_AR
                if self._is_arabic(question)
                else NO_DOCUMENT_CONTEXT_EN
            )

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
            text = await self.vision.answer_question(
                image_bytes=image["image_data"],
                image_description=description,
                history=history,
                question=question,
                documents_context=context if route == "BOTH" else "",
            )
            return {"answer": text, "sources": sources if route == "BOTH" else []}

        # Text path: STUDY vs DOCS
        if route == "STUDY":
            system_content = (

        "You are STUDY GATE AI, an educational assistant.\n"
        "- Answer the student's question clearly and directly, "
        "in the same language as the student.\n"
        "- The context below is optional. Use it only if it is clearly "
        "relevant to the question; otherwise answer from your general "
        "knowledge and do not mention any uploaded files.\n"
        "- When the student asks to summarize a PDF, document, lecture, "
        "or uploaded file, treat it as a summarization request.\n"
        "- Summarize the actual relevant document content provided in "
        "the context. Combine relevant parts into a coherent summary.\n"
        "- Do not interpret 'summarize PDF' as a question about PDFs.\n"
        "- Never invent document content or claim that no PDF information "
        "exists when relevant document content is available.\n"
        "- If the context is incomplete, summarize only what is available "
        "and mention that the summary is partial.\n\n"
        "## Response format\n"
        "- Start with a direct answer in 1-2 sentences.\n"
        "- Match the length to the question: a simple question gets a short "
        "answer without headings; use ### headings only when the answer has "
        "3 or more distinct parts.\n"
        "- Reply in the same Arabic dialect the student writes in "
        "(Egyptian if they write Egyptian, Modern Standard Arabic if they write MSA). "
        "Use a different dialect only if the student explicitly asks for it.\n"
        "- Write natural, fluent Arabic, not a word-for-word translation.\n"
        "- Keep technical terms, subject/course names, person names, acronyms and "
        "code in English inline inside the Arabic sentence. Never translate them "
        "and never repeat them in parentheses.\n"
        "- Proofread: no typos.\n"
        "- Put every key term in **bold** the first time it appears.\n"
        "- Use bullet points for real lists only, one idea per bullet, each "
        "- Do not add sections the student did not ask for (applications, "
        "summaries).\n"
        "- Teaching style: when an example would help the student understand, "
        "give one short example or analogy (1-2 lines) that is close to the "
        "student's own question and easy to relate to, not a generic one. "
        "If the question is simple and direct, or an example adds nothing, "
        "skip it. For problems, solve step by step, one line per step.\n"
        "- Be concise: no filler, no repeating the question.\n"
        "- Never end mid-sentence. If the answer is long, keep only the "
        "most important points.\n"
        "- Never end with a menu of options or a follow-up question.\n"
        "- Do not use emojis.\n"
        "- If the student asks a personal question (like their name), "
        "answer it in one short sentence.\n"
        "- When the student asks for code: write one short intro sentence, "
        "then give the complete code together in one continuous block "
        "(one block per file, back to back, each labeled only with its "
        "filename), then at most 3 short bullets explaining the key parts. "
        "Never put explanation between code blocks or split one program "
        "into sections with headings.\n"
        "- Give code examples only when the student asks for code or when code is necessary to explain a programming topic.\n"
        "- Keep code examples short, but never limit complete code to 10 lines.\n\n"
        f"## Optional context\n{context or 'None'}"
        + (f"\n\n## Image description\n{image_description}" if image_description else "")
                    )
                      
            prompt = question
        else:
            base_system_prompt = self.nlp.template_parser.get("rag", "system_prompt")
            reply_language = "Arabic" if self._is_arabic(question) else "English"
            system_content = (
                f"{base_system_prompt}\n\n"
                "## Relevant project documents\n"
                "## Rules\n"
                "- The documents above are the student's uploaded files. "
                "'Summarize the PDF/file/lecture' means summarize their content.\n"
                "- Never say the documents contain no PDF or file.\n"
                "- If the content is partial, say the summary is partial.\n"
                "- Answer once: a short intro, then bullet points.\n\n"
                "- Do not mention file names or page numbers in the answer; sources are attached separately."
                f"## Language\nWrite in {reply_language}, the language of the student's "
                "current question, even if the documents are in another language.\n"
                "- In Arabic, write natural, fluent Arabic, not a word-for-word translation.\n"
                "- Reply in the same Arabic dialect the student writes in "
                "(Egyptian if they write Egyptian, Modern Standard Arabic if they write MSA). "
                "Use a different dialect only if the student explicitly asks for it.\n"
                "- Keep technical terms, subject/course names, person names, acronyms and "
                "code in English exactly as written in the source, inline inside the Arabic "
                "sentence. Never translate them and never repeat them in parentheses.\n"
                "- Proofread: no typos."
            )
            prompt = (
                f"{footer_prompt}\n\n## Relevant Document Context\n{context}"
                if footer_prompt
                else question
            )

        system_message = {"role": "system", "content": system_content}
        stream_kwargs = {"on_token": on_token} if on_token else {}
        # First attempt
        answer = await asyncio.to_thread(

            self.generation_client.generate_text,

            prompt=prompt,

            chat_history=[system_message] + history,

        )

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

                **stream_kwargs,
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


        return {
            "answer": answer.strip(),
            "sources": sources if route in ("DOCS", "BOTH", "STUDY") else [],
            }                        

    @staticmethod
    def _build_search_query(question: str, history: list) -> str:
        if len(question.split()) >= 2 :
            return question
        for message in reversed(history):
            if message["role"] == "user" and message["content"].strip() != question.strip():
                return f"{message['content']} {question}"
        return question

    @staticmethod
    def _build_sources(metas: list) -> list:
     files = {}
     for m in metas:
         if isinstance(m, str):
             try:
                 m = json.loads(m)
             except ValueError:
                 m = {}
         m = m or {}
         name = os.path.basename(str(m.get("source") or m.get("file_name") or ""))
         if not name:
             continue
         pages = files.setdefault(name, set())
         page = m.get("page")
         if isinstance(page, int):
             pages.add(page + 1)  # الـ loaders بتبدأ من 0
     return [{"file": n, "pages": sorted(p)} for n, p in files.items()]