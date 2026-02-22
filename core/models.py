from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=True)
    unit = Column(String, nullable=True)
    store = Column(String, nullable=True)
    category = Column(String, nullable=True)
    metadata_ = Column("metadata", SQLITE_JSON, nullable=True)
