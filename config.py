import os

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
SLACK_APP_TOKEN = os.environ.get('SLACK_APP_TOKEN')
SLACK_SOCKET_MODE = os.environ.get('SLACK_SOCKET_MODE')
SLACK_ASYNC_APP = os.environ.get('SLACK_ASYNC_APP')

REDIS_URL = os.environ.get('REDIS_URL')
SENTRY_DSN = os.environ.get('SENTRY_DSN')
SERVER_PORT = int(os.environ.get("PORT", 4000))
