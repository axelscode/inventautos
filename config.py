class Config:
    # Cambiar de MySQL a SQLite
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "inventautos.db")}'
    SECRET_KEY = 'inventautos_secret_key_2024'
    SESSION_TYPE = 'filesystem'