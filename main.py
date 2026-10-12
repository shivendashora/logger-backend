from fastapi import FastAPI, File, Form, UploadFile,Depends,HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import os

from helper.authHelper import hash_password,verify_password,create_token
from database import Base, engine
import tables.models  # registers the models on Base.metadata so create_all can see them

from tables.models import UsersTable,UsersLog,fileAttachments

from database import sessionLocal
app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def get_db():
    db = sessionLocal()
    try:
        yield db
        
    finally:
        db.close()


@app.on_event('startup')
def startup():

    print("triggering the startup command")
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Server is running at port 3000"}


@app.post('/login')
@app.post('/login')
def login(form_Data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db)):
    user = db.query(UsersTable).filter(UsersTable.username == form_Data.username).first()

    if not user or not verify_password(form_Data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="invalid username or password")

    return {
        "access_token": create_token(user.id),
        "token_type": "bearer",
    }

@app.post('/sign-in')
def sign_in(username: str, password: str, email: str, db = Depends(get_db)):

    if not username or not password or not email:
        raise HTTPException(status_code=400, detail="required fields are not present")

    existing = db.query(UsersTable).filter(UsersTable.email == email).first()
    if existing:
        return {"message": "user already exists"}

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
def update_card(name:str,description:str,token = Depends(oauth2_scheme)):
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
    token = Depends(oauth2_scheme)
    ):
    print("recieved data from user structuring and saving data to db",name, description)
    print("recieved file name",file.filename)

    return {
        "message":"Message logged successfully ",
        "data": {"name": name, "description": description}
    }

