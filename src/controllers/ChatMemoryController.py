from sqlalchemy import text


class ChatMemoryController:
    async def ensure_tables(self, db_client):
        async with db_client() as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id BIGSERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    conversation_id VARCHAR(100) NOT NULL,
                    role VARCHAR(20) NOT NULL
                        CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_chat_messages_history
                ON chat_messages
                    (project_id, conversation_id, message_id DESC)
            """))

            await session.commit()

    async def get_history(
        self, db_client, project_id: int, conversation_id: str,
        limit: int = 10
    ) -> list:
        async with db_client() as session:
            result = await session.execute(
                text("""
                    SELECT role, content
                    FROM chat_messages
                    WHERE project_id = :project_id
                      AND conversation_id = :conversation_id
                    ORDER BY message_id DESC
                    LIMIT :limit
                """),
                {
                    "project_id": project_id,
                    "conversation_id": conversation_id,
                    "limit": limit,
                },
            )
            rows = result.mappings().all()

            return [
                {"role": row["role"], "content": row["content"]}
                for row in reversed(rows)
            ]

    async def save_message(
        self, db_client, project_id: int, conversation_id: str,
        role: str, content: str
    ):
        async with db_client() as session:
            await session.execute(
                text("""
                    INSERT INTO chat_messages
                        (project_id, conversation_id, role, content)
                    VALUES
                        (:project_id, :conversation_id, :role, :content)
                """),
                {
                    "project_id": project_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "content": content,
                },
            )
            await session.commit()
