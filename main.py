from fastapi import FastAPI, File, Form, UploadFile,Depends,HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

from helper.authHelper import hash_password,verify_password,create_token,parse_jwt
from jwt import ExpiredSignatureError,InvalidTokenError
from database import Base, engine
import tables.models  # registers the models on Base.metadata so create_all can see them

from tables.models import UsersTable,UsersLog,fileAttachments
from helper.normalHelper import create_file_path, validate_upload, original_file_name
from fastapi.responses import FileResponse
from database import sessionLocal

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



@app.get('/get-logs')
def getLogs(user = Depends(get_current_user),db = Depends(get_db)):

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User does not exist"
        )

    # outer join so a log without an attachment still comes back (with file_path None)
    data = (
        db.query(UsersLog, fileAttachments.filePath, fileAttachments.fileType)
        .outerjoin(fileAttachments, fileAttachments.id == UsersLog.fileAttachmentsId)
        .filter(UsersLog.user_id == user.id)
        .order_by(UsersLog.created_at.desc())
        .all()
    )

    return {
        "message":"Here are the logs",
        "data":[
            {
                "id": log.id,
                "name": log.log_name,
                "description": log.log_description,
                "file_path": file_path,
                "file_url": file_url(file_path),
                "file_type": file_type,
                "created_at": log.created_at,
            }
            for log, file_path, file_type in data
        ]
    }


@app.get('/logs/{log_id}/download')
def download_log_file(log_id: int, user = Depends(get_current_user), db = Depends(get_db)):
    # only the owner of the log can download its attachment
    attachment = (
        db.query(fileAttachments)
        .join(UsersLog, UsersLog.fileAttachmentsId == fileAttachments.id)
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

    if file and file.filename:
        # reject anything that isn't a real PDF or image before it touches the disk
        try:
            file_type = validate_upload(file)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        response = create_file_path(file, directory_path)

        if response:
            file_attachment = fileAttachments(
                user_id=user.id,
                filePath=response,
                fileType=file_type
            )

            db.add(file_attachment)
            db.flush()

    log_object = UsersLog(
        log_name=name,
        log_description=description,
        user_id=user.id,
        fileAttachmentsId=file_attachment.id if file_attachment else None
    )

    db.add(log_object)
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


