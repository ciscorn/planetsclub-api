from starlette.config import Config

config = Config(".env")

DEBUG = config("DEBUG", cast=bool, default=False)

SECRET_KEY = config("SECRET_KEY")

REDIS_URL = config("REDIS_URL")

ELASTICSEARCH_HOSTS = config("ELASTICSEARCH_HOSTS").split(",")
ELASTICSEARCH_HTTP_AUTH = tuple(config("ELASTICSEARCH_HTTP_AUTH").split(":"))
ELASTICSEARCH_USE_SSL = config("ELASTICSEARCH_USE_SSL", cast=bool, default=True)
