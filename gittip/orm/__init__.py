from __future__ import unicode_literals
import os

from sqlalchemy import create_engine, event, MetaData
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import Pool



dburl = os.environ['DATABASE_URL']
db_engine = create_engine(dburl)

Session = scoped_session(sessionmaker())
Session.configure(bind=db_engine)

Base = declarative_base()
Base.metadata.bind = db_engine
Base.query = Session.query_property()

metadata = MetaData()
metadata.bind = db_engine


all = [
    Base, Session, metadata
]
