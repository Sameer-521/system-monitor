from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    poller_interval: int = 1  # in seconds
    ticket_lifetime: int = 300  # in seconds
    cpu_buffer_interval_window: int = 120  # in seconds (2mins)


_settings = Settings()
