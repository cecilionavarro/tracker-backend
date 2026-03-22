from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  app_name: str = "Tracker"
  debug: bool = True
  MONGO_URI: str
  DB_NAME: str

  # this too
  # class Config:
  #       env_file = ".env"
  model_config = SettingsConfigDict(env_file=".env")

settings = Settings()