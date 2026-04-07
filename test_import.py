import sys
print("Python executable:", sys.executable)
print("Python version:", sys.version)
try:
    import fastapi
    print("FastAPI version:", fastapi.__version__)
    import openai
    print("OpenAI imported successfully")
    from main import app
    print("App imported successfully")
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
