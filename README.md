# mini-rag
RAG tutorial for beginner AI Engineers that shift their capabilities from just deeling with Notebooks to produce real applications and deploy it

## Requirements

  - Python 3.8 or later

### Install Python using miniconda

1) Download and install miniconda from [here](https://www.anaconda.com/docs/getting-started/miniconda/install#quickstart-install-instructions)
2) Creat a new environment using this command:
"""bash 
   $ conda create -n mini-rag python==3.8
"""
3) Activate the invironment:
"""bash
   $ y
"""

#### Installation
1) Install the required packages.
"""bash
   $ pip install -r requirements.txt
"""
2) Setup the environment variables
"""bash
   $ cp .env.example .env
"""
3) Set your environment variables in the .env file. Like OPENAI_API_KEY value.

##### Run the FastAPI server
"""bash
   $ uvicorn main:app --reload --host 0.0.0.0 --port 5000
"""