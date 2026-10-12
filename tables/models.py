from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from database import Base

class BaseColumns(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class UsersTable(BaseColumns):
    __tablename__ = "users"

    id = Column(Integer,primary_key=True,autoincrement=True)
    username = Column(String)
    email = Column(String)
    hashed_password = Column(String)


class UsersLog(BaseColumns):
    __tablename__ = "userlog"

    id = Column(Integer,primary_key=True,autoincrement=True)
    user_id = Column(Integer,ForeignKey("users.id"))
    email = Column(String)
    hashed_password = Column(String)


class fileAttachments(BaseColumns):
    __tablename__ = "fileAttachments"

    id = Column(Integer,primary_key=True,autoincrement=True)
    user_id = Column(Integer,ForeignKey("users.id"))
    log_id = Column(Integer,ForeignKey("userlog.id"))
    filePath = Column(String)
    fileType = Column(String)
 
