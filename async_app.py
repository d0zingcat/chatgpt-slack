from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import SocketModeHandler

import config


def init_async_app():
    return AsyncApp(
        token=config.SLACK_BOT_TOKEN,
        signing_secret=config.SLACK_SIGNING_SECRET,
    )


async_app = init_async_app()
async_handler = SocketModeHandler(async_app, config.SLACK_APP_TOKEN)
