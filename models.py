from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Float
from sqlalchemy import Text

from database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    category = Column(String(100))
    description = Column(Text)
    ingredients = Column(Text)
    instructions = Column(Text)    
    image_url = Column(Text)
    rating = Column(Float)
    difficulty = Column(String(50))
    cost = Column(String(50))
    prep_time = Column(String(100))
    tags = Column(Text)
    
    @property
    def tags_list(self):
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]