--
-- PostgreSQL database dump
--

\restrict 94N2nEVgqB7gCGMMtjkjCBCEd8OiKbZtSg6QcXBmR9wAcTbhmtLPcfpockv20Ph

-- Dumped from database version 17.6 (Debian 17.6-1.pgdg12+1)
-- Dumped by pg_dump version 17.6 (Debian 17.6-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: celery_task_executions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.celery_task_executions (
    execution_id integer NOT NULL,
    task_name character varying(255) NOT NULL,
    task_args_hash character varying(64) NOT NULL,
    celery_task_id uuid,
    status character varying(20) NOT NULL,
    task_args jsonb,
    result jsonb,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.celery_task_executions OWNER TO postgres;

--
-- Name: celery_task_executions_execution_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.celery_task_executions_execution_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.celery_task_executions_execution_id_seq OWNER TO postgres;

--
-- Name: celery_task_executions_execution_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.celery_task_executions_execution_id_seq OWNED BY public.celery_task_executions.execution_id;


--
-- Name: celery_task_executions execution_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.celery_task_executions ALTER COLUMN execution_id SET DEFAULT nextval('public.celery_task_executions_execution_id_seq'::regclass);


--
-- Data for Name: celery_task_executions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.celery_task_executions (execution_id, task_name, task_args_hash, celery_task_id, status, task_args, result, started_at, completed_at, created_at, updated_at) FROM stdin;
59	tasks.file_processing.process_project_files	3667d279abfa9fcafbb1637199c4cf181aa663ca9957b9912d9f124681655608	e8845432-a489-4c5a-ae08-721d7d1e28a2	SUCCESS	{"card_id": 1, "file_id": 2, "do_reset": 0, "chunk_size": 1000, "project_id": 1, "overlap_size": 50}	{"signal": "processing_success"}	2026-11-20 13:15:20.792819+00	2026-11-20 13:15:20.874806+00	2026-11-20 13:15:20.795966+00	2026-11-20 13:15:20.873762+00
\.


--
-- Name: celery_task_executions_execution_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.celery_task_executions_execution_id_seq', 59, true);


--
-- Name: celery_task_executions celery_task_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.celery_task_executions
    ADD CONSTRAINT celery_task_executions_pkey PRIMARY KEY (execution_id);


--
-- Name: ixz_celery_task_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ixz_celery_task_id ON public.celery_task_executions USING btree (celery_task_id);


--
-- Name: ixz_task_execution_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ixz_task_execution_created_at ON public.celery_task_executions USING btree (created_at);


--
-- Name: ixz_task_execution_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ixz_task_execution_status ON public.celery_task_executions USING btree (status);


--
-- Name: ixz_task_name_args_celery_hash; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ixz_task_name_args_celery_hash ON public.celery_task_executions USING btree (task_name, task_args_hash, celery_task_id);


--
-- Name: ixz_task_name_args_hash; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ixz_task_name_args_hash ON public.celery_task_executions USING btree (task_name, task_args_hash);


--
-- PostgreSQL database dump complete
--

\unrestrict 94N2nEVgqB7gCGMMtjkjCBCEd8OiKbZtSg6QcXBmR9wAcTbhmtLPcfpockv20Ph

