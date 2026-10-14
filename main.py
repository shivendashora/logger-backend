from datetime import datetime

from fastapi import FastAPI, File, Form, Query, UploadFile,Depends,HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os
from sqlalchemy import or_

from helper.authHelper import hash_password,verify_password,create_token,parse_jwt
from jwt import ExpiredSignatureError,InvalidTokenError
from database import Base, engine
import tables.models  # registers the models on Base.metadata so create_all can see them

from tables.models import UsersTable,UsersLog,fileAttachments
from helper.normalHelper import clean_search_query, create_file_path, validate_upload, original_file_name
from fastapi.responses import FileResponse
from database import sessionLocal


class LogItem(BaseModel):
    id: int
    name: str
    description: str
    file_path: str | None
    file_url: str | None
    file_type: str | None
    created_at: datetime | None


class PaginatedResponse(BaseModel):
    offset: int = Field(0, ge=0)          # rows skipped
    limit: int = Field(10, ge=1, le=50)   # rows per page
    total: int                            # all of the user's logs, ignoring offset/limit
    data: list[LogItem]


directory_path = r"C:\Users\shive\OneDrive\Desktop\react-revision\logger\logger-backend\Uploads" 

app = FastAPI()
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


def get_db():
    db = sessionLocal()
    try:
        yield db
        
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)):
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
    user = db.query(UsersTable).filter(UsersTable.id == int(user_id)).first() if user_id else None
    if not user:
        raise credentials_error

    return user


@app.on_event('startup')
def startup():

    print("triggering the startup command")
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Server is running at port 3000"}

@app.post('/login')
def login(form_Data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db)):
    # the OAuth2 form field is called "username", but the frontend sends the email in it
    user = db.query(UsersTable).filter(UsersTable.email == form_Data.username).first()

    if not user or not verify_password(form_Data.password, user.hashed_password):
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
def sign_in(body: SignUpRequest, db = Depends(get_db)):
    username, email, password = body.username, body.email, body.password

    if not username or not password or not email:
        raise HTTPException(status_code=400, detail="required fields are not present")

    existing = db.query(UsersTable).filter(UsersTable.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="user already exists")

    db.add(UsersTable(
        username=username,
        hashed_password=hash_password(password),
        email=email,
    ))
    db.commit()

    return {
        "message": "user sign-in successfull",
        "data": {"username": username, "email": email},
    }



@app.get('/get-logs', response_model=PaginatedResponse)
def getLogs(
    user = Depends(get_current_user),
    db = Depends(get_db),
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
    logs_query = db.query(UsersLog).filter(UsersLog.user_id == user.id)

    if processedQuery:
        # case-insensitive search in the log's name or description
        logs_query = logs_query.filter(or_(
            UsersLog.log_name.icontains(processedQuery),
            UsersLog.log_description.icontains(processedQuery),
        ))

    total = logs_query.count()

    # outer join so a log without an attachment still comes back (with file_path None);
    # offset/limit run in SQL so only one page is loaded, and id breaks ties in created_at
    data = (
        logs_query
        .outerjoin(fileAttachments, fileAttachments.log_id == UsersLog.id)
        .add_columns(fileAttachments.filePath, fileAttachments.fileType)
        .order_by(UsersLog.created_at.desc(), UsersLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return PaginatedResponse(
        offset=offset,
        limit=limit,
        total=total,
        data=[
            LogItem(
                id=log.id,
                name=log.log_name,
                description=log.log_description,
                file_path=file_path,
                file_url=file_url(file_path),
                file_type=file_type,
                created_at=log.created_at,
            )
            for log, file_path, file_type in data
        ],
    )


@app.get('/logs/{log_id}/download')
def download_log_file(log_id: int, user = Depends(get_current_user), db = Depends(get_db)):
    # only the owner of the log can download its attachment
    attachment = (
        db.query(fileAttachments)
        .join(UsersLog, UsersLog.id == fileAttachments.log_id)
        .filter(UsersLog.id == log_id, UsersLog.user_id == user.id)
        .first()
    )

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
def delete_logs(body: DeleteLogsRequest, user = Depends(get_current_user), db = Depends(get_db)):
    # filtering by user_id means ids belonging to someone else are silently skipped
    logs = db.query(UsersLog).filter(UsersLog.id.in_(body.ids), UsersLog.user_id == user.id).all()
    if not logs:
        raise HTTPException(status_code=404, detail="No matching logs found")

    deleted_ids = [log.id for log in logs]
    # read the file paths first: the attachment rows disappear with their logs
    file_paths = [
        attachment.filePath
        for attachment in db.query(fileAttachments).filter(fileAttachments.log_id.in_(deleted_ids)).all()
    ]

    # ON DELETE CASCADE on fileAttachments.log_id removes the attachment rows in the database
    for log in logs:
        db.delete(log)
    db.commit()

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


@app.post('/update-card')
def update_card(name:str,description:str,user = Depends(get_current_user)):
    return{
        "message":"updated card details",
        "details":{
            "name":name,
            "description":description
        }
    }



@app.post('/logFormData')
def log_message(
    name: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    print(
        "Received data:",
        name,
        description
    )
    print("Received file:", file.filename)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User does not exist"
        )

    file_attachment = None

    # validate before anything is written, so a bad file creates neither a log nor a file on disk
    file_type = None
    if file and file.filename:
        # reject anything that isn't a real PDF or image before it touches the disk
        try:
            file_type = validate_upload(file)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # the log is created first so the attachment can point at it (fileAttachments.log_id)
    log_object = UsersLog(
        log_name=name,
        log_description=description,
        user_id=user.id,
    )
    db.add(log_object)
    db.flush()

    if file_type:
        response = create_file_path(file, directory_path)

        if response:
            file_attachment = fileAttachments(
                user_id=user.id,
                log_id=log_object.id,
                filePath=response,
                fileType=file_type
            )
            db.add(file_attachment)

    db.commit()
    db.refresh(log_object)

    return {
        "message": "Message logged successfully",
        "data": {
            "id": log_object.id,
            "name": name,
            "description": description,
            "file_path": response if file_attachment else None,
            "file_url": file_url(response) if file_attachment else None,
            "file_type": file_attachment.fileType if file_attachment else None
        }
    }


