# =============================================================================
# This module defines the Product model using SQLAlchemy's declarative base. 
# The Product class represents a product in the database with fields for id, product_id, name, price, unit, store, category, and metadata. 
# The metadata field is stored as JSON in the SQLite database. 
# This model is used for storing and retrieving product information during the application's operation.
# It runs after the initial data parsing and before the scoring and optimization phases, which rely on this structured product data.
# =============================================================================

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
