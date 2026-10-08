# Mini-Rag

this project implement rag application for question answering

## Requirements

- Python 3.8 or more

### Install Python Using Miniconda

1) Download Miniconda from [here](https://www.anaconda.com/docs/getting-started/installation)
2) Create a new environment using the following commands
```bash
$ conda create -n mini-rag python=3.8
```
3) Activate the environment
```bash
$ conda activate mini-rag
```

### (Optional) Setup your command line interface for more readability
```bash
export PS1="\[\033[01;32m\]\u@\h:\w\n\[\033[00m\]\$ "
``` 

## Installations

### Install the Required Packages
```bash
$ pip install -r requirements.txt
```

### Setup the Environment Variables
```bash
$ cp .env.example .env
```

Set the Environment Variables Like OPENAI_API_KEY

## Run the FastAPI Server

```bash
$ uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

## Run Docker Compose Service

```bash
$ cd docker
$ cp .env.example .env
```

- update ".env" with your credentials