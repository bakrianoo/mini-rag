 # mini-rag

 This is aminial implementation of the RAG model for question 
 answering.

 ## Requirements
 - python 3.8 or later

 ### Install python Using Miniconda

 1) Download and install Miniconda from [here] (https:// docs.anaconda.com/free/Miniconda/# quick-cpmmand-line-install)

 2) Create a new environment using the following command :
  
    ```bash
    $ conda create -n mini-rag python=3.8
    ```
 3) Activate the environment :

    ```bash
    $ conda activate mini-rag-app
    ```
 4) Deactivate environment
    ```bash
    $ conda deactivate
    ```
    
#### export PS1="\[\033[01;32m\]\u@\h:\w\n\[\033[00m\]\$"


## Insallation

### Install the required packages

```bash
pip install -r requirements.txt
```
### setup the environment variable
```bash
cp .env.example .env
```
Set your invrionment variable in the `.env` file. like `OPEMAI_API_KYE` value.

### Run the FastAPI server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```