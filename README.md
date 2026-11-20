## Requirements

- Python 3.12

#### Install Dependencies

```bash
source .venv/bin/activate
source .venv/bin/activate
```

```bash
sudo apt update
sudo apt install libpq-dev gcc python3-dev
```

#### Install Python using MiniConda

1) Download and install MiniConda from [here](https://docs.anaconda.com/free/miniconda/#quick-command-line-install)
2) Create a new environment using the following command:
```bash
$ conda create -n mini-rag python=3.10
```
3) Activate the environment:
```bash
$ conda activate mini-rag
```

### (Optional) Setup you command line interface for better readability

```bash
export PS1="\[\033[01;32m\]\u@\h:\w\n\[\033[00m\]\$ "
```


## Installation

### Install the required packages

```bash
$ pip install -r requirements.txt
```

### Setup the environment variables

```bash
$ cp .env.example .env
```


## Run Docker Compose Services

```bash
$ cd docker
$ cp .env.example .env
```

- update `.env` with your credentials



```bash
$ cd docker
$ sudo docker compose up -d
$ docker compose restart
$ docker compose logs -f fastapi
$ docker compose up -d --build fastapi celery-worker
$ docker compose restart fastapi
$ docker compose up -d --force-recreate fastapi celery-worker
$ docker compose logs -f celery-worker | grep -v clean_celery
$ docker compose exec pgvector psql -U postgres -d minirag -c "TRUNCATE TABLE chunks, assets CASCADE;"






$  docker compose exec pgvector psql -U postgres -d minirag -c "
TRUNCATE TABLE chunks, assets RESTART IDENTITY CASCADE;
SELECT COUNT(*) AS remaining_assets FROM assets;
SELECT COUNT(*) AS remaining_chunks FROM chunks;
SELECT COALESCE(MAX(asset_id), 0) AS last_asset_id FROM assets;
"


$ docker compose exec pgvector psql -U postgres -d minirag -c "
TRUNCATE TABLE vision_messages, vision_images RESTART IDENTITY CASCADE;
"
```

## Access Services

- **FastAPI**: http://localhost:8000
- **Flower Dashboard**: http://localhost:5555 (admin/password from env)
- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090

## keep alive
$ curl http://localhost:11434/api/generate -d '{"model": "granite4.2:8b", "keep_alive": -1}' 

## Run the FastAPI server (Development Mode)

```bash
$ uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

# Celery (Development Mode)

For development, you can run Celery services manually instead of using Docker:

To Run the **Celery worker**, you need to run the following command in a separate terminal:

```bash
$ python -m celery -A celery_app worker --queues=default,file_processing,data_indexing --loglevel=info
```

To run the **Beat scheduler**, you can run the following command in a separate terminal:

```bash
$ python -m celery -A celery_app beat --loglevel=info
```

To Run **Flower Dashboard**, you can run the following command in a separate terminal:

```bash
$ python -m celery -A celery_app flower --conf=flowerconfig.py
```


open your browser and go to `http://localhost:5555` to see the dashboard.

## POSTMAN Collection

Download the POSTMAN collection from [/assets/mini-rag-app.postman_collection.json](/assets/mini-rag-app.postman_collection.json)

## Features

Mini RAG is a study workspace API. A project is the unit of work: documents, images, quizzes, and study plans all belong to one project.

| Capability | What it does |
| --- | --- |
| Projects | Creates an isolated workspace and returns its numeric id and UUID. |
| Document ingestion | Accepts a file, chunks it, and indexes the chunks in the vector store. |
| Retrieval and answers | Searches indexed content and answers questions from the retrieved passages. |
| Board upload | Reads images with a vision model, and indexes PDF and TXT files on a study card. |
| Unified chat | One conversation endpoint for answers, quiz generation, single-answer checks, and full quiz submission. Optional token streaming. |
| Quizzes | Builds multiple-choice questions from indexed material or image descriptions, then scores answers. |
| Study planner | Extracts an exam schedule from an image or text, stores the reviewed schedule, and generates a day-by-day study plan. |

Interactive docs are available at `/docs` (Swagger) and `/redoc` once the API is running.

## API reference

Base path: `/api/v1`

Docker serves the API at `http://localhost:8000`. The development server in this guide uses port `5000`.

Most routes require a `project_id` created by `POST /api/v1/projects`. A missing project returns `404` with `{"detail": "Project not found."}`. Planner routes use the same status and a `signal` field instead of `detail`.

Background work (chunking and indexing) returns a Celery task id. Poll the board status route for board uploads, or Flower for worker tasks.

### Service

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/` | Returns `app_name` and `app_version`. |
| `GET` | `/docs` | Swagger UI. |
| `GET` | `/redoc` | ReDoc. |
| `GET` | `/TrhBVe_m5gg2002_E5VVqS` | Prometheus metrics. Hidden from the OpenAPI schema. |

### Projects

#### `POST /api/v1/projects`

Creates a project. No request body.

**201**

```json
{
  "project_id": 1,
  "project_uuid": "00000000-0000-0000-0000-000000000000"
}
```

### Data

#### `POST /api/v1/data/upload/{project_id}`

Uploads one document. `multipart/form-data` with a `file` field.

**200** `{ "signal": "file_upload_success", "file_id": "12" }`

**400** when the file type or size is rejected, or the write fails.

#### `POST /api/v1/data/process/{project_id}`

Chunks an uploaded file in the background.

```json
{
  "file_id": "12",
  "card_id": 1,
  "chunk_size": 100,
  "overlap_size": 20,
  "do_reset": 0
}
```

`chunk_size`, `overlap_size`, and `do_reset` are optional. `do_reset` of `1` clears existing chunks before processing.

**200** `{ "signal": "processing_success", "task_id": "<celery-task-id>" }`

#### `POST /api/v1/data/process-and-push/{project_id}`

Chunks the file and indexes it in one background workflow. Same body as process.

**200** `{ "signal": "process_and_push_workflow_ready", "workflow_task_id": "<celery-task-id>" }`

### NLP and retrieval

#### `POST /api/v1/nlp/index/push/{project_id}`

Indexes chunks that were already processed.

```json
{
  "do_reset": 0,
  "card_id": 1,
  "file_id": 12
}
```

`card_id` and `file_id` are required.

**200** `{ "signal": "data_push_task_ready", "task_id": "<celery-task-id>" }`

**400** `{ "detail": "card_id and file_id are required." }`

#### `GET /api/v1/nlp/index/info/{project_id}`

Returns vector collection metadata.

**200** `{ "signal": "vectordb_collection_retrieved", "collection_info": {} }`

#### `POST /api/v1/nlp/index/search/{project_id}`

Similarity search over indexed chunks.

```json
{
  "text": "What is photosynthesis?",
  "limit": 5,
  "card_id": 1
}
```

`limit` defaults to `5`. `card_id` is optional.

**200** `{ "signal": "vectordb_search_success", "results": [] }`

**400** when the search returns nothing.

#### `POST /api/v1/nlp/index/answer/{project_id}`

Retrieval-augmented answer. Same body as search. `card_id` scopes retrieval to one study card when set.

**200**

```json
{
  "signal": "rag_answer_success",
  "answer": "...",
  "full_prompt": "...",
  "chat_history": []
}
```

**400** when no answer can be produced.

#### `DELETE /api/v1/nlp/index/reset/{project_id}`

Drops the project's vector collection.

**200** `{ "signal": "VECTORDB_COLLECTION_RESET", "result": true }`

### Board

#### `POST /api/v1/board/upload/{project_id}`

Uploads one or more files for a study card. `multipart/form-data`.

| Field | Required | Notes |
| --- | --- | --- |
| `file` | yes | Repeat the field for multiple files. Image, PDF, or TXT. 10 MB each. |
| `card_id` | no | Defaults to `1`. |
| `session_id` | no | Created when omitted. `conversation_id` is accepted as an alias. |

Images are described by the vision model and stored with the session. PDF and TXT files are saved as assets and sent through the process-and-push workflow. The request waits up to 30 seconds for that workflow.

**200**

```json
{
  "project_id": 1,
  "session_id": "<uuid>",
  "card_id": 1,
  "conversation_id": "<uuid>",
  "total_files": 1,
  "results": []
}
```

Each image result includes `image_id`, `filename`, and `description`. Each document result includes `document_id`, `workflow_task_id`, and `status` (`processing`, `done`, or `failed`).

**400** empty upload, unsupported type, or empty file. **413** over 10 MB. **502** vision analysis failed. **500** document save failed.

#### `GET /api/v1/board/status/{task_id}`

Polls a board workflow task.

**200** `{ "status": "processing" }` or `{ "status": "done", "card_id": 1 }` or `{ "status": "failed", "card_id": 1 }`

### Chat

#### `POST /api/v1/chat/{project_id}`

Single entry point for conversation and quiz actions. Set `stream` to `true` to receive Server-Sent Events (`token`, then `done` or `error`) instead of one JSON body.

```json
{
  "card_id": 1,
  "action": "chat",
  "question": "Explain the diagram on this card.",
  "conversation_id": null,
  "stream": false,
  "quiz_id": null,
  "question_id": null,
  "answer": null,
  "answers": null,
  "question_count": 5,
  "difficulty": "medium",
  "topic": null
}
```

| Field | Notes |
| --- | --- |
| `card_id` | Required. Positive integer. |
| `action` | `chat` (default), `generate_quiz`, `answer_question`, or `submit_quiz`. |
| `question` | Required for `chat`. Up to 10,000 characters. |
| `conversation_id` | Reuse to keep history. A new id is created when omitted. |
| `question_count` | 1–20. Default `5`. Used by `generate_quiz`. |
| `difficulty` | `easy`, `medium`, or `hard`. |
| `quiz_id` | Required for `answer_question` and `submit_quiz`. |
| `question_id`, `answer` | Required for `answer_question`. `answer` is `A`, `B`, `C`, or `D`. |
| `answers` | Required for `submit_quiz`. Map of question id to `A`–`D`. |

**200** `type` is `text`, `quiz`, `answer_result`, or `quiz_result`.

```json
{
  "signal": "CHAT_ANSWER_SUCCESS",
  "project_id": 1,
  "conversation_id": "<uuid>",
  "type": "text",
  "answer": "..."
}
```

Quiz actions return `CHAT_QUIZ_SUCCESS`, `QUIZ_ANSWER_CHECKED`, or `QUIZ_SUBMITTED`, with `quiz` or `result` instead of `answer`.

**400** missing fields. **404** unknown project, quiz, or card image. **502** generation failure.

### Quiz

These routes are the direct quiz API. The chat endpoint can perform the same three actions.

#### `POST /api/v1/quiz/generate/{project_id}`

```json
{
  "card_id": 1,
  "question_count": 5,
  "difficulty": "medium",
  "topic": "Chapter 2"
}
```

`question_count` is 1–10. `difficulty` is `easy`, `medium`, or `hard`. `topic` is optional.

**201** `{ "signal": "QUIZ_GENERATED", "quiz": {} }`

**400** no source material for the card. **502** the model output could not be validated.

#### `POST /api/v1/quiz/answer/{project_id}/{quiz_id}`

Checks one question.

```json
{
  "question_id": "q1",
  "answer": "B"
}
```

**200** `{ "signal": "ANSWER_CHECKED", "result": {} }`

**404** `{ "signal": "QUIZ_NOT_FOUND" }`

**400** `{ "signal": "INVALID_QUIZ_ANSWER", "detail": "..." }`

#### `POST /api/v1/quiz/submit/{project_id}/{quiz_id}`

Scores the full quiz.

```json
{
  "answers": {
    "q1": "B",
    "q2": "A"
  }
}
```

**200** `{ "signal": "QUIZ_SUBMITTED", "result": {} }`

**404** `{ "signal": "QUIZ_NOT_FOUND" }`

**400** `{ "signal": "INVALID_QUIZ_ANSWERS", "detail": "..." }`

### Study planner

Extract, review, then save. Plan generation reads only the saved schedule. Saving a new schedule marks the current plan stale. Deleting the schedule also deletes its plan. A plan is no longer returned after the last exam date.

#### `POST /api/v1/planner/extract/{project_id}`

Reads exams from an image or from text. Nothing is stored. `multipart/form-data` with either `file` (image, max 5 MB) or `text` (max 5,000 characters), not both.

**200**

```json
{
  "signal": "SCHEDULE_EXTRACTED",
  "exams": [
    { "subject": "Biology", "exam_date": "2026-06-12", "exam_time": "09:00:00" }
  ]
}
```

**400** `PLANNER_NO_INPUT`, `PLANNER_TEXT_TOO_LONG`, `PLANNER_FILE_TYPE_NOT_SUPPORTED`, `PLANNER_FILE_SIZE_INVALID`, or `SCHEDULE_NOT_FOUND_IN_INPUT`.

**502** `SCHEDULE_EXTRACTION_ERROR`.

#### `PUT /api/v1/planner/schedule/{project_id}`

Replaces the project's saved exams. 1–30 items.

```json
{
  "exams": [
    { "subject": "Biology", "exam_date": "2026-06-12", "exam_time": "09:00:00" }
  ]
}
```

`exam_time` may be `null`. `subject` is 1–255 characters.

**200** `{ "signal": "SCHEDULE_SAVED", "exams": [] }`

#### `GET /api/v1/planner/schedule/{project_id}`

**200** `{ "signal": "SCHEDULE_FETCHED", "exams": [] }`

#### `DELETE /api/v1/planner/schedule/{project_id}`

Deletes the schedule and the plan built from it.

**200** `{ "signal": "SCHEDULE_DELETED" }`

**404** `{ "signal": "SCHEDULE_NOT_FOUND" }`

#### `POST /api/v1/planner/generate/{project_id}`

Builds a study plan from the saved schedule and stores it.

```json
{
  "note": "4 hours a day, rest on Friday, start tomorrow",
  "today": "2026-06-01"
}
```

`note` is optional, up to 500 characters. The planner reads hours per day, rest weekdays, a start offset, and focus subjects from it. `today` is the student's local date (`YYYY-MM-DD`) and is used only when it is within one day of the server's UTC date.

**200**

```json
{
  "signal": "PLAN_GENERATED",
  "plan": { "days": [] },
  "preferences": {
    "focus_subjects": [],
    "unapplied": [],
    "start_in_days": 0
  },
  "note": null,
  "is_stale": false,
  "expires_on": "2026-06-12",
  "updated_at": "2026-06-01T00:00:00"
}
```

**400** `SCHEDULE_NOT_SAVED` when nothing is stored, or `PLAN_INPUT_INVALID`.

**504** `PLAN_GENERATION_TIMEOUT`. **502** `PLAN_GENERATION_ERROR`.

#### `GET /api/v1/planner/plan/{project_id}`

Returns the active plan. When none exists, `plan` is `null` and `signal` is `PLAN_NOT_CREATED_YET`. The other keys stay present so the response shape does not change.

**200** `PLAN_FETCHED` or `PLAN_NOT_CREATED_YET`.

#### `DELETE /api/v1/planner/plan/{project_id}`

Deletes the study plan and leaves the exam schedule in place.

**200** `{ "signal": "PLAN_DELETED" }`

**404** `{ "signal": "PLAN_NOT_FOUND" }`

