from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def welcom ():
    return {"massege":"Welcome  to FastAPI!"}