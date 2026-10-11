from fastapi import FastAPI, File, Form, UploadFile,Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionMaker
import os


DB_URL = ""

engine = create_engine(DB_URL)

app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


@app.get("/")
def root():
    return {"message": "Server is running at port 3000"}



@app.post('/login')
def login(form_Data : OAuth2PasswordRequestForm = Depends()):
    return{
        "message":"login sucessfull",
        "data":{
            "username":form_Data.username,
            "password":form_Data.password
        }
    }
@app.post('/sign-in')
def sign_in(username:str,password:str,email:str):
    return{
        "message":"user sign-in successfull",
        "data":{
            "username":username,
            "password":password,
            "email":email
        }
    }
    

@app.post('/update-card')
def update_card(name:str,description:str):
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
    file: UploadFile = File(...)
    ):
    print("recieved data from user structuring and saving data to db",name, description)
    print("recieved file name",file.filename)

    return {
        "message":"Message logged successfully ",
        "data": {"name": name, "description": description}
    }

