from fastapi import FastAPI, File, Form, UploadFile,Depends,HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

from helper.authHelper import hash_password,verify_password,create_token,parse_jwt
from jwt import ExpiredSignatureError,InvalidTokenError
from database import Base, engine
import tables.models  # registers the models on Base.metadata so create_all can see them

from tables.models import UsersTable,UsersLog,fileAttachments

from database import sessionLocal
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


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
    description:str = Form(...),
    file: UploadFile = File(...),
    user = Depends(get_current_user)
    ):
    print("recieved data from user structuring and saving data to db",name, description)
    print("recieved file name",file.filename)

    return {
        "message":"Message logged successfully ",
        "data": {"name": name, "description": description}
    }

