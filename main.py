from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, File, Form, Query, UploadFile,Depends,HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os
from sqlalchemy import insert, or_, select

from helper.authHelper import hash_password,verify_password,create_token,parse_jwt
from jwt import ExpiredSignatureError,InvalidTokenError
from database import Base, engine, get_db_session
import tables.models  # registers the models on Base.metadata so create_all can see them

from tables.models import UsersTable,UsersLog,fileAttachments
from helper.normalHelper import clean_search_query, create_file_path, validate_upload, original_file_name
from fastapi.responses import FileResponse


class LogItem(BaseModel):
    id: int
    name: str
    description: str
    file_path: str | None
    file_url: str | None
    file_type: str | None
    created_at: datetime | None


class PaginatedResponse(BaseModel):
    offset: int = Field(0, ge=0)          
    limit: int = Field(10, ge=1, le=50)   
    total: int                            
    data: list[LogItem]


directory_path = r"C:\Users\shive\OneDrive\Desktop\react-revision\logger\logger-backend\Uploads" 

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    print("Disposing engine")
    await engine.dispose()

app = FastAPI(
    lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# serve saved attachments at /uploads/<file name> so the frontend can show them
os.makedirs(directory_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=directory_path), name="uploads")


def file_url(file_path):
    # turns a saved file's disk path into the URL it's served at
    return f"/uploads/{os.path.basename(file_path)}" if file_path else None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login"
                                                                  )



async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db_session)):
    # decodes the bearer token and loads its user; any failure is a 401
    credentials_error = HTTPException(
        status_code=401,
        detail="invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = parse_jwt(token)
    except (ExpiredSignatureError, InvalidTokenError):
        raise credentials_error

    user_id = payload.get("sub")

    

    query = select(UsersTable).where(UsersTable.id == int(user_id))

    user = await db.execute(query)
    return user.scalar_one_or_none() 


@app.get("/")
def root():
    return {"message": "Server is running at port 3000"}

@app.post('/login')
async def login(form_Data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db_session)):
    # the OAuth2 form field is called "username", but the frontend sends the email in it

    query = select(UsersTable).where(UsersTable.email == form_Data.username)
    user =  await db.execute(query)
    user = user.scalar_one_or_none()

    if not user or not await verify_password(form_Data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="invalid username or password")

    return {
        "message": "login successfully",
        "access_token": create_token(user.id),
        "token_type": "bearer",
    }
class SignUpRequest(BaseModel):
    username: str
    email: str
    password: str


@app.post('/sign-in')
async def sign_in(body: SignUpRequest, db = Depends(get_db_session)):
    username, email, password = body.username, body.email, body.password

    if not username or not password or not email:
        raise HTTPException(status_code=400, detail="required fields are not present")

    existing = await db.execute(select(UsersTable).where(UsersTable.email == email))
    existing = existing.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="user already exists")

    query = insert(UsersTable).values(
        username=username,
        email=email,
        hashed_password=await hash_password(password),
    ).returning(UsersTable.username,UsersTable.email)

    user = await db.execute(query)
    user=user.one()

    print(f'User created: {user}')
    await db.commit()

    return {
        "message": "user sign-in successfull",
        "data": {"username": user.username, "email": user.email},
    }



@app.get('/get-logs')
async def getLogs(
    user = Depends(get_current_user),
    db = Depends(get_db_session),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    searchQuery: str | None = Query(None, max_length=100),
):

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User does not exist"
        )

    processedQuery = clean_search_query(searchQuery)

    # one base query, so the total and the page always use the same filters
    query = select(UsersLog).where(
    UsersLog.user_id == user.id,
    UsersLog.log_name.ilike(f"%{processedQuery}%") if processedQuery else True
    ).order_by(UsersLog.created_at.desc()).offset(offset).limit(limit)


    logs_query = await db.execute(query)
    logs_query = logs_query.scalars().all()


    logData=[]

    for log in logs_query:
        attachment = await db.execute(select(fileAttachments).where(fileAttachments.log_id == log.id))
        attachment = attachment.scalar_one_or_none()

        logData.append(
            LogItem(
                id=log.id,
                name=log.log_name,
                description=log.log_description,
                file_path=attachment.filePath if attachment else None,
                file_url=file_url(attachment.filePath) if attachment else None,
                file_type=attachment.fileType if attachment else None,
                created_at=log.created_at,
            )
        )

    print(f"Total logs for user {user.id}:",len(logData))
    return PaginatedResponse(
        offset=offset,
        limit=limit,
        total=len(logData),
        data=logData,
    )


@app.get('/logs/{log_id}/download')
async def download_log_file(log_id: int, user = Depends(get_current_user), db = Depends(get_db_session)):
    # only the owner of the log can download its attachment
    attachment = (
        await db.execute(select(fileAttachments)
        .join(UsersLog, UsersLog.id == fileAttachments.log_id)
        .where(UsersLog.id == log_id, UsersLog.user_id == user.id))
    ).scalars().first()

    if not attachment or not os.path.exists(attachment.filePath):
        raise HTTPException(status_code=404, detail="File not found")

    # filename= makes the browser save it under its original name
    return FileResponse(
        attachment.filePath,
        media_type=attachment.fileType,
        filename=original_file_name(attachment.filePath),
    )


class DeleteLogsRequest(BaseModel):
    ids: list[int]


@app.post('/logs/delete')
async def delete_logs(body: DeleteLogsRequest, user = Depends(get_current_user), db = Depends(get_db_session)):
    # filtering by user_id means ids belonging to someone else are silently skipped
    logs = (await db.execute(select(UsersLog).where(UsersLog.id.in_(body.ids), UsersLog.user_id == user.id))).scalars().all()
    if not logs:
        raise HTTPException(status_code=404, detail="No matching logs found")

    deleted_ids = [log.id for log in logs]
    # read the file paths first: the attachment rows disappear with their logs
    file_paths = (
        await db.execute(select(fileAttachments.filePath).where(fileAttachments.log_id.in_(deleted_ids)))
    ).scalars().all()

    # ON DELETE CASCADE on fileAttachments.log_id removes the attachment rows in the database
    for log in logs:
        await db.delete(log)
    await db.commit()

    # remove files only after the commit, so a failed delete never loses a file that's still referenced
    for file_path in file_paths:
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass

    return {
        "message": f"Deleted {len(deleted_ids)} log(s)",
        "data": {"deleted_ids": deleted_ids},
    }


@app.get('/logs/{log_id}', response_model=LogItem)
async def get_log(log_id: int, user = Depends(get_current_user), db = Depends(get_db_session)):
    # one log by id (used when a card page is opened directly); only the owner can read it
    # .first() on the result (not .scalars()) keeps the whole (log, file_path, file_type) row
    row = (
        await db.execute(select(UsersLog, fileAttachments.filePath, fileAttachments.fileType)
        .outerjoin(fileAttachments, fileAttachments.log_id == UsersLog.id)
        .where(UsersLog.id == log_id, UsersLog.user_id == user.id))
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Log not found")

    log, file_path, file_type = row
    return LogItem(
        id=log.id,
        name=log.log_name,
        description=log.log_description,
        file_path=file_path,
        file_url=file_url(file_path),
        file_type=file_type,
        created_at=log.created_at,
    )


class UpdateLogRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=10000)


@app.put('/logs/{log_id}')
async def update_log(log_id: int, body: UpdateLogRequest, user = Depends(get_current_user), db = Depends(get_db_session)):
    # only the owner can edit; someone else's id looks the same as a missing one
    log = (await db.execute(select(UsersLog).where(UsersLog.id == log_id, UsersLog.user_id == user.id))).scalars().first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name can't be empty")

    log.log_name = name
    log.log_description = body.description
    await db.commit()
    await db.refresh(log)

    return {
        "message": "Log updated",
        "data": {"id": log.id, "name": log.log_name, "description": log.log_description},
    }



@app.post('/logFormData')
async def log_message(
    name: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db=Depends(get_db_session)
):
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User does not exist"
        )

    saved_path = None

    # validate before anything is written, so a bad file creates neither a log nor a file on disk
    file_type = None
    if file and file.filename:
        # reject anything that isn't a real PDF or image before it touches the disk
        try:
            file_type = validate_upload(file)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # the log is created first so the attachment can point at it (fileAttachments.log_id)
    query = select(UsersLog).where(UsersLog.user_id == user.id, UsersLog.log_name == name)
    existing_log = (await db.execute(query)).scalar_one_or_none()

    if existing_log:
        raise HTTPException(status_code=409, detail="Log with the same name already exists")
    
    query = insert(UsersLog).values(
        log_name=name,
        log_description=description,
        user_id=user.id,
    ).returning(UsersLog.id)

    log_id = (await db.execute(query)).scalar()

    if file_type:
        saved_path = await create_file_path(file, directory_path)

        if saved_path:
            query = insert(fileAttachments).values(
                user_id=user.id,
                log_id=log_id,
                filePath=saved_path,
                fileType=file_type
            )
            await db.execute(query)

    await db.commit()

    return {
        "message": "Message logged successfully",
        "data": {
            "id": log_id,
            "name": name,
            "description": description,
            "file_path": saved_path,
            "file_url": file_url(saved_path),
            "file_type": file_type if saved_path else None
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)