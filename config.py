from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_model: str = "groq/llama-3.3-70b-versatile"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_temperature: float = 0.2
    llm_max_tokens: int = 500

    # Provider bootstrap
    admin_phone: str
    admin_name: str
    business_type: str = "trainer"
    location_type: str = "mobile"
    auto_book: bool = False
    buffer_mins: int = 15
    working_hours: str = '{"mon":["09:00","18:00"],"tue":["09:00","18:00"],"wed":["09:00","18:00"],"thu":["09:00","18:00"],"fri":["09:00","18:00"]}'

    # Optional
    google_maps_api_key: str = ""
    linq_api_token: str = ""
    linq_phone_number: str = ""
    linq_developer_phone: str = ""

    port: int = 8000

    class Config:
        env_file = None


settings = Settings()
