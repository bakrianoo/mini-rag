from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def welcom ():
    return {"Welcome  to FastAPI!"}