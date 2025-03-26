from fastapi import FastAPI

app = FastAPI()

@app.get("/welcome")
def welcome():
    return{ 
        "message": "Welcome Ahmed in FastAPI trip!"
    }
