from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from routes import base, nlp, chat, board, quiz, planner, projects, auth
from utils.auth import get_current_user, limit_gemini_usage
from utils.internal_auth import verify_internal_key, check_internal_key_configured
from helpers.config import get_settings
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.llm.templates.template_parser import TemplateParser
from utils.metrics import setup_metrics

app = FastAPI()

# Setup Prometheus metrics
setup_metrics(app)


async def startup_span():
    check_internal_key_configured()
    settings = get_settings()

    host = settings.POSTGRES_HOST.split("?")[0]
    dbname = settings.POSTGRES_MAIN_DATABASE.split("?")[0]
    print(f"DEBUG host={host!r} db={dbname!r} port={settings.POSTGRES_PORT}", flush=True)
    db_url = URL.create(
        "postgresql+asyncpg",
        username=settings.POSTGRES_USERNAME,
        password=settings.POSTGRES_PASSWORD,
        host=host,
        port=int(settings.POSTGRES_PORT),
        database=dbname,
    )

    connect_args = {}
    if "neon.tech" in host:
        connect_args["ssl"] = "require"
    if "-pooler" in host:
        connect_args["statement_cache_size"] = 0

    app.db_engine = create_async_engine(
        db_url, connect_args=connect_args, pool_pre_ping=True
    )
    app.db_client = sessionmaker(
        app.db_engine, class_=AsyncSession, expire_on_commit=False
    )

    llm_provider_factory = LLMProviderFactory(settings)
    vectordb_provider_factory = VectorDBProviderFactory(config=settings, db_client=app.db_client)

    # generation client
    app.generation_client = llm_provider_factory.create(provider=settings.GENERATION_BACKEND)
    app.generation_client.set_generation_model(model_id=settings.GENERATION_MODEL_ID)

    # embedding client
    app.embedding_client = llm_provider_factory.create(provider=settings.EMBEDDING_BACKEND)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )

    # vector db client
    app.vectordb_client = vectordb_provider_factory.create(
        provider=settings.VECTOR_DB_BACKEND
    )
    await app.vectordb_client.connect()

    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANG,
        default_language=settings.DEFAULT_LANG,
    )


async def shutdown_span():
    await app.db_engine.dispose()
    await app.vectordb_client.disconnect()


app.on_event("startup")(startup_span)
app.on_event("shutdown")(shutdown_span)

app.include_router(base.base_router)
app.include_router(auth.auth_router, dependencies=[Depends(verify_internal_key)])
app.include_router(nlp.nlp_router, dependencies=[Depends(verify_internal_key), Depends(limit_gemini_usage)])
app.include_router(board.board_router, dependencies=[Depends(verify_internal_key), Depends(limit_gemini_usage)])
app.include_router(chat.chat_router, dependencies=[Depends(verify_internal_key), Depends(limit_gemini_usage)])
app.include_router(quiz.quiz_router, dependencies=[Depends(verify_internal_key), Depends(limit_gemini_usage)])
app.include_router(projects.projects_router, dependencies=[Depends(verify_internal_key), Depends(get_current_user)])
app.include_router(planner.planner_router, dependencies=[Depends(verify_internal_key), Depends(limit_gemini_usage)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)