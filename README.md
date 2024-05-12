# mini-rag

This is a minimal implementation of the RAG model for question answering.

## The Course

This is an educational project where all of the codes where explained (step by step) via a set of `Arabic` youtube videos. Please check the list:

| # | Title                                    | Link                                                                                                 | Codes                                              |
|---|------------------------------------------|------------------------------------------------------------------------------------------------------|----------------------------------------------------|
| 1 | About the Course ماذا ولمـــاذا          | [Video](https://www.youtube.com/watch?v=Vv6e2Rb1Q6w&list=PLvLvlVqNQGHCUR2p0b8a0QpVjDUg50wQj)         | NA                                                 |
| 2 | What will we build ماذا سنبنى في المشروع | [Video](https://www.youtube.com/watch?v=_l5S5CdxE-Q&list=PLvLvlVqNQGHCUR2p0b8a0QpVjDUg50wQj&index=2) | NA                                                 |
| 3 | Setup your tools الأدوات الأساسية        | [Video](https://www.youtube.com/watch?v=VSFbkFRAT4w&list=PLvLvlVqNQGHCUR2p0b8a0QpVjDUg50wQj&index=3) | NA                                                 |
| 4 | Project Architecture                     | [Video](https://www.youtube.com/watch?v=Ei_nBwBbFUQ&list=PLvLvlVqNQGHCUR2p0b8a0QpVjDUg50wQj&index=4) | [branch](https://github.com/bakrianoo/mini-rag/tree/tut-001) |
| 5 | Welcome to FastAPI                       | [Video](https://www.youtube.com/watch?v=cpOuCdzN_Mo&list=PLvLvlVqNQGHCUR2p0b8a0QpVjDUg50wQj&index=5) | [branch](https://github.com/bakrianoo/mini-rag/tree/tut-002) |
| 6 | Nested Routes + Env Values               | [Video](https://www.youtube.com/watch?v=CrR2Bz2Y7Hw&list=PLvLvlVqNQGHCUR2p0b8a0QpVjDUg50wQj&index=6) | [branch](https://github.com/bakrianoo/mini-rag/tree/tut-003) |
| 7 | Uploading a File                         | [Video](https://www.youtube.com/watch?v=5alMKCbFqWs&list=PLvLvlVqNQGHCUR2p0b8a0QpVjDUg50wQj&index=7) | [branch](https://github.com/bakrianoo/mini-rag/tree/tut-004) |




## Requirements

- Python 3.8 or later

#### Install Python using MiniConda

1) Download and install MiniConda from [here](https://docs.anaconda.com/free/miniconda/#quick-command-line-install)
2) Create a new environment using the following command:
```bash
$ conda create -n mini-rag python=3.8
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

Set your environment variables in the `.env` file. Like `OPENAI_API_KEY` value.

## Run the FastAPI server

```bash
$ uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

## POSTMAN Collection

Download the POSTMAN collection from [/assets/mini-rag-app.postman_collection.json](/assets/mini-rag-app.postman_collection.json)
