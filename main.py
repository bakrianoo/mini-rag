from fastapi import FastAPI
app = FastAPI()

@app.get("/welcome")
def wellcome():
    return{
        "message" : "Hello World!"
    }