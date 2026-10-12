import datetime

import bcrypt
import jwt
from jwt import ExpiredSignatureError,InvalidTokenError

secrete_key = "secrete-key"
algorithm  = "HS256"
Access_token_expiry_time = 30




def hash_password(password:str):
     # return hashed password

     salt = bcrypt.gensalt()
     hashed_password = bcrypt.hashpw(password.encode("utf-8"),salt)
     return hashed_password.decode("utf-8")


def verify_password(password:str,hashed_password:str):
     # return hashed password

     return bcrypt.checkpw(
          password.encode("utf-8"),hashed_password.encode("utf-8")
     )


def create_token(user_id:str):
     #creates token 

     expiry  = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes= Access_token_expiry_time)
     to_encode  = {
          "sub": str(user_id),
          "exp": expiry
     }

     return jwt.encode(to_encode,secrete_key,algorithm=algorithm)

def parse_jwt(token:str):
     return jwt.decode(token,secrete_key,algorithms=[algorithm])


