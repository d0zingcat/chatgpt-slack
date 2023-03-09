import logging
import asyncio

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

import config
from async_app import app as async_app

logging.basicConfig(level=logging.DEBUG)

if config.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,

        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0
    )


async def async_run():
    async_handler = AsyncSocketModeHandler(async_app, config.SLACK_APP_TOKEN)
    await async_handler.start_async()

if __name__ == "__main__":
    asyncio.run(async_run())
    async_app.start(port=config.SERVER_PORT)
