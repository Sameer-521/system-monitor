from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    poller_interval: int = 1  # in seconds
    ticket_lifetime: int = 300  # in seconds


_settings = Settings()
