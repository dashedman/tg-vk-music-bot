from sqlalchemy import create_engine

from root.db_models import Base


def init_db():
    engine = create_engine('sqlite:///../tracks_data_base.db')
    Base.metadata.create_all(engine)


if __name__ == '__main__':
    init_db()
