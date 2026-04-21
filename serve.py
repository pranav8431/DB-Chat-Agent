from src.db_chat_agent.web.app import app


if __name__ == "__main__":
    uvicorn = __import__("uvicorn")
    uvicorn.run(app, host="0.0.0.0", port=8000)
