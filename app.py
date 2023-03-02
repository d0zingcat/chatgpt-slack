import logging


import config
from sync_app import app, handler
from async_app import async_app, async_handler

logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    if bool(config.SLACK_ASYNC_APP):
        if bool(config.SLACK_SOCKET_MODE):
            async_handler.start()
        async_app.start(port=config.SERVER_PORT)
    else:
        if bool(config.SLACK_SOCKET_MODE):
            handler.start()
        app.start(port=config.SERVER_PORT)  # POST http://localhost:3000/slack/events
