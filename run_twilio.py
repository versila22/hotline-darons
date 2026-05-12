import uvicorn
from bot.twilio_webhook import app

if __name__ == "__main__":
    uvicorn.run("bot.twilio_webhook:app", host="0.0.0.0", port=8000, reload=True)
