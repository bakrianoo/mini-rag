from sqlalchemy import text


class VisionMemoryController:

    async def ensure_tables(self, db_client):
        async with db_client() as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS vision_images (
                    image_id BIGSERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    session_id VARCHAR(100) NOT NULL,
                    filename TEXT NOT NULL,
                    mime_type VARCHAR(100) NOT NULL,
                    image_data BYTEA NOT NULL,
                    description TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))

            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS vision_messages (
                    message_id BIGSERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    session_id VARCHAR(100) NOT NULL,
                    image_id BIGINT NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_vision_images_session
                ON vision_images (project_id, session_id, image_id)
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_vision_messages_session
                ON vision_messages (
                    project_id, session_id, message_id
                )
            """))

            await session.commit()

    async def save_image(
        self,
        db_client,
        project_id: int,
        session_id: str,
        filename: str,
        mime_type: str,
        image_data: bytes,
        description: str,
    ):
        async with db_client() as session:
            result = await session.execute(
                text("""
                    INSERT INTO vision_images (
                        project_id, session_id, filename,
                        mime_type, image_data, description
                    )
                    VALUES (
                        :project_id, :session_id, :filename,
                        :mime_type, :image_data, :description
                    )
                    RETURNING image_id, created_at
                """),
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "filename": filename,
                    "mime_type": mime_type,
                    "image_data": image_data,
                    "description": description,
                },
            )
            record = result.mappings().one()
            await session.commit()
            return dict(record)

    async def get_latest_image(
        self, db_client, project_id: int, session_id: str
    ):
        async with db_client() as session:
            result = await session.execute(
                text("""
                    SELECT image_id, filename, mime_type,
                           image_data, description
                    FROM vision_images
                    WHERE project_id = :project_id
                      AND session_id = :session_id
                    ORDER BY image_id DESC
                    LIMIT 1
                """),
                {
                    "project_id": project_id,
                    "session_id": session_id,
                },
            )
            record = result.mappings().first()
            return dict(record) if record else None

    async def get_latest_project_image(self, db_client, project_id: int):
        async with db_client() as session:
            result = await session.execute(
                text("""
                    SELECT image_id, filename, mime_type,
                           image_data, description, session_id
                    FROM vision_images
                    WHERE project_id = :project_id
                    ORDER BY image_id DESC
                    LIMIT 1
                """),
                {"project_id": project_id},
            )
            record = result.mappings().first()
            return dict(record) if record else None

    async def get_history(
        self, db_client, project_id: int, session_id: str,
        image_id: int, limit: int = 10
    ):
        async with db_client() as session:
            result = await session.execute(
                text("""
                    SELECT role, content
                    FROM vision_messages
                    WHERE project_id = :project_id
                      AND session_id = :session_id
                      AND image_id = :image_id
                    ORDER BY message_id DESC
                    LIMIT :limit
                """),
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "image_id": image_id,
                    "limit": limit,
                },
            )
            records = result.mappings().all()
            return [
                {"role": row["role"], "content": row["content"]}
                for row in reversed(records)
            ]

    async def save_message(
        self, db_client, project_id: int, session_id: str,
        image_id: int, role: str, content: str
    ):
        async with db_client() as session:
            await session.execute(
                text("""
                    INSERT INTO vision_messages (
                        project_id, session_id, image_id, role, content
                    )
                    VALUES (
                        :project_id, :session_id, :image_id, :role, :content
                    )
                """),
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "image_id": image_id,
                    "role": role,
                    "content": content,
                },
            )
            await session.commit()
