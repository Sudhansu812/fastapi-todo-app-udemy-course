from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    LOG_DIR: str = "./logs"
    CONNECTION_STRING: str = "sqlite:///./todos.db"
    MYSQL_HOST: str="localhost"
    MSSQL_HOST: str="localhost"
    PGSQL_HOST: str="localhost"

    MYSQL_DB: str="todo"
    MSSQL_DB: str="todo"
    PGSQL_DB: str="todo"

    MYSQL_PORT: int=3306
    MSSQL_PORT: int=1433
    PGSQL_PORT: int=5432

    MYSQL_PASSWORD: str=""
    PGSQL_PASSWORD: str=""
    MSSQL_PASSWORD: str=""
    
    JWT_SECRET: str=""
    ALGORITHM: str="HS256"

    class Config:
        env_file= os.path.join(os.path.dirname(__file__), "..", "..", "env", ".env")

    @property
    def sqlite_url(self) -> str:
        return self.CONNECTION_STRING

    @property
    def mysql_url(self) -> str:
        return f"mysql+pymysql://root:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?allowPublicKeyRetrieval=true"

    @property
    def postgres_url(self) -> str:
        return f"postgresql+psycopg://postgres:{self.PGSQL_PASSWORD}@{self.PGSQL_HOST}:{self.PGSQL_PORT}/{self.PGSQL_DB}"

    @property
    def mssql_url(self) -> str:
        return f"mssql+pyodbc://sa:{self.MSSQL_PASSWORD}@{self.MSSQL_HOST}:{self.MSSQL_PORT}/{self.MSSQL_DB}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

    @property
    def jwt_secret(self) -> str:
        return self.JWT_SECRET
    
    @property
    def algorithm(self) -> str:
        return self.ALGORITHM

settings = Settings()