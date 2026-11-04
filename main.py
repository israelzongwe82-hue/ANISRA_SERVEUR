import os, uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt, JWTError

DB=os.getenv("DATABASE_URL","sqlite:///./anisra.db")
if DB.startswith("postgres://"): DB=DB.replace("postgres://","postgresql://",1)
engine=create_engine(DB,connect_args={"check_same_thread":False} if DB.startswith("sqlite") else {},pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,autoflush=False,autocommit=False)
SECRET=os.getenv("ANISRA_SECRET_KEY","DEV_ONLY_CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT")
pwd=CryptContext(schemes=["bcrypt"],deprecated="auto")
oauth=OAuth2PasswordBearer(tokenUrl="/auth/login")
app=FastAPI(title="ANISRA API",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","*").split(",")],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
class Base(DeclarativeBase): pass
class User(Base):
 __tablename__="users"
 id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
 username:Mapped[str]=mapped_column(String(32),unique=True,index=True)
 display_name:Mapped[str]=mapped_column(String(80))
 email:Mapped[Optional[str]]=mapped_column(String(254),unique=True,nullable=True,index=True)
 phone:Mapped[Optional[str]]=mapped_column(String(32),unique=True,nullable=True,index=True)
 password_hash:Mapped[str]=mapped_column(String(255))
 created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Contact(Base):
 __tablename__="contacts"
 id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
 owner_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
 contact_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
class Invitation(Base):
 __tablename__="invitations"
 id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
 sender_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
 receiver_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
 status:Mapped[str]=mapped_column(String(20),default="pending")
 created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Message(Base):
 __tablename__="messages"
 id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
 sender_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
 receiver_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
 body:Mapped[str]=mapped_column(Text)
 created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Group(Base):
 __tablename__="groups"
 id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
 name:Mapped[str]=mapped_column(String(100))
 owner_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
class GroupMember(Base):
 __tablename__="group_members"
 id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
 group_id:Mapped[str]=mapped_column(ForeignKey("groups.id"),index=True)
 user_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
class GroupMessage(Base):
 __tablename__="group_messages"
 id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
 group_id:Mapped[str]=mapped_column(ForeignKey("groups.id"),index=True)
 sender_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
 body:Mapped[str]=mapped_column(Text)
 created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
Base.metadata.create_all(engine)
def db():
 s=SessionLocal()
 try: yield s
 finally: s.close()
class Register(BaseModel):
 username:str=Field(min_length=3,max_length=32,pattern=r"^[a-zA-Z0-9_.-]+$")
 display_name:str=Field(min_length=1,max_length=80)
 password:str=Field(min_length=10,max_length=128)
 email:Optional[EmailStr]=None
 phone:Optional[str]=Field(default=None,max_length=32)
class Login(BaseModel):
 login:str
 password:str
class Invite(BaseModel): receiver_id:str
class Msg(BaseModel):
 receiver_id:str
 body:str=Field(min_length=1,max_length=10000)
class GroupIn(BaseModel): name:str=Field(min_length=1,max_length=100)
class GroupMsg(BaseModel): body:str=Field(min_length=1,max_length=10000)
def view(u): return {"id":u.id,"username":u.username,"display_name":u.display_name,"email":u.email,"phone":u.phone}
def make_token(u):
 n=datetime.now(timezone.utc)
 return jwt.encode({"sub":u.id,"iat":n,"exp":n+timedelta(days=7)},SECRET,algorithm="HS256")
def auth(token:str=Depends(oauth),s:Session=Depends(db)):
 try: uid=jwt.decode(token,SECRET,algorithms=["HS256"]).get("sub")
 except JWTError: raise HTTPException(401,"Session invalide ou expirée.")
 u=s.get(User,uid) if uid else None
 if not u: raise HTTPException(401,"Compte introuvable.")
 return u
@app.get("/")
def home(): return {"service":"ANISRA API","status":"online"}
@app.get("/health")
def health(): return {"ok":True}
@app.post("/auth/register")
def register(d:Register,s:Session=Depends(db)):
 if not d.email and not d.phone: raise HTTPException(400,"Ajoutez un e-mail ou un téléphone.")
 if s.query(User).filter(User.username==d.username).first(): raise HTTPException(409,"Nom d'utilisateur déjà utilisé.")
 if d.email and s.query(User).filter(User.email==d.email).first(): raise HTTPException(409,"E-mail déjà utilisé.")
 if d.phone and s.query(User).filter(User.phone==d.phone).first(): raise HTTPException(409,"Téléphone déjà utilisé.")
 u=User(username=d.username,display_name=d.display_name,email=d.email,phone=d.phone,password_hash=pwd.hash(d.password))
 s.add(u);s.commit();s.refresh(u)
 return {"access_token":make_token(u),"token_type":"bearer","user":view(u)}
@app.post("/auth/login")
def login(d:Login,s:Session=Depends(db)):
 u=s.query(User).filter((User.username==d.login)|(User.email==d.login)|(User.phone==d.login)).first()
 if not u or not pwd.verify(d.password,u.password_hash): raise HTTPException(401,"Identifiants incorrects.")
 return {"access_token":make_token(u),"token_type":"bearer","user":view(u)}
@app.get("/me")
def me(u:User=Depends(auth)): return view(u)
@app.get("/users/search")
def search(q:str,s:Session=Depends(db),u:User=Depends(auth)):
 if len(q.strip())<2: raise HTTPException(400,"Saisissez au moins deux caractères.")
 rows=s.query(User).filter(User.id!=u.id,(User.username.ilike(f"%{q}%"))|(User.display_name.ilike(f"%{q}%"))).limit(25).all()
 return [view(x) for x in rows]
@app.post("/invitations")
def invite(d:Invite,s:Session=Depends(db),u:User=Depends(auth)):
 if d.receiver_id==u.id or not s.get(User,d.receiver_id): raise HTTPException(404,"Utilisateur introuvable.")
 old=s.query(Invitation).filter_by(sender_id=u.id,receiver_id=d.receiver_id,status="pending").first()
 if old:return {"id":old.id,"status":old.status}
 x=Invitation(sender_id=u.id,receiver_id=d.receiver_id);s.add(x);s.commit();s.refresh(x)
 return {"id":x.id,"status":x.status}
@app.get("/invitations")
def list_invites(s:Session=Depends(db),u:User=Depends(auth)):
 return [{"id":x.id,"sender_id":x.sender_id,"receiver_id":x.receiver_id,"status":x.status} for x in s.query(Invitation).filter((Invitation.sender_id==u.id)|(Invitation.receiver_id==u.id)).all()]
@app.post("/invitations/{iid}/{action}")
def answer_invite(iid:str,action:str,s:Session=Depends(db),u:User=Depends(auth)):
 x=s.get(Invitation,iid)
 if not x or x.receiver_id!=u.id: raise HTTPException(404,"Invitation introuvable.")
 if action not in ("accept","decline") or x.status!="pending": raise HTTPException(400,"Action impossible.")
 x.status="accepted" if action=="accept" else "declined"
 if action=="accept":
  for a,b in ((x.sender_id,x.receiver_id),(x.receiver_id,x.sender_id)):
   if not s.query(Contact).filter_by(owner_id=a,contact_id=b).first():s.add(Contact(owner_id=a,contact_id=b))
 s.commit();return {"status":x.status}
@app.get("/contacts")
def contacts(s:Session=Depends(db),u:User=Depends(auth)):
 ids=[x.contact_id for x in s.query(Contact).filter_by(owner_id=u.id).all()]
 return [view(s.get(User,i)) for i in ids if s.get(User,i)]
@app.post("/messages")
def send(d:Msg,s:Session=Depends(db),u:User=Depends(auth)):
 if not s.query(Contact).filter_by(owner_id=u.id,contact_id=d.receiver_id).first():raise HTTPException(403,"Vous devez d'abord être contacts.")
 m=Message(sender_id=u.id,receiver_id=d.receiver_id,body=d.body);s.add(m);s.commit();s.refresh(m)
 return {"id":m.id,"sender_id":m.sender_id,"receiver_id":m.receiver_id,"body":m.body,"created_at":m.created_at.isoformat()}
@app.get("/messages/{other_id}")
def history(other_id:str,s:Session=Depends(db),u:User=Depends(auth)):
 rows=s.query(Message).filter(((Message.sender_id==u.id)&(Message.receiver_id==other_id))|((Message.sender_id==other_id)&(Message.receiver_id==u.id))).order_by(Message.created_at.asc()).limit(500).all()
 return [{"id":m.id,"sender_id":m.sender_id,"receiver_id":m.receiver_id,"body":m.body,"created_at":m.created_at.isoformat()} for m in rows]
@app.post("/groups")
def create_group(d:GroupIn,s:Session=Depends(db),u:User=Depends(auth)):
 g=Group(name=d.name,owner_id=u.id);s.add(g);s.flush();s.add(GroupMember(group_id=g.id,user_id=u.id));s.commit();s.refresh(g)
 return {"id":g.id,"name":g.name,"owner_id":u.id}
@app.post("/groups/{gid}/members/{uid}")
def add_member(gid:str,uid:str,s:Session=Depends(db),u:User=Depends(auth)):
 g=s.get(Group,gid)
 if not g or g.owner_id!=u.id:raise HTTPException(403,"Seul le créateur peut ajouter des membres.")
 if not s.get(User,uid):raise HTTPException(404,"Utilisateur introuvable.")
 if not s.query(GroupMember).filter_by(group_id=gid,user_id=uid).first():s.add(GroupMember(group_id=gid,user_id=uid));s.commit()
 return {"ok":True}
@app.post("/groups/{gid}/messages")
def group_send(gid:str,d:GroupMsg,s:Session=Depends(db),u:User=Depends(auth)):
 if not s.query(GroupMember).filter_by(group_id=gid,user_id=u.id).first():raise HTTPException(403,"Accès refusé.")
 m=GroupMessage(group_id=gid,sender_id=u.id,body=d.body);s.add(m);s.commit();s.refresh(m)
 return {"id":m.id,"group_id":gid,"sender_id":u.id,"body":m.body,"created_at":m.created_at.isoformat()}
@app.get("/groups/{gid}/messages")
def group_history(gid:str,s:Session=Depends(db),u:User=Depends(auth)):
 if not s.query(GroupMember).filter_by(group_id=gid,user_id=u.id).first():raise HTTPException(403,"Accès refusé.")
 return [{"id":m.id,"sender_id":m.sender_id,"body":m.body,"created_at":m.created_at.isoformat()} for m in s.query(GroupMessage).filter_by(group_id=gid).order_by(GroupMessage.created_at.asc()).limit(500).all()]
@app.post("/files")
async def upload(file:UploadFile=File(...),u:User=Depends(auth)):
 data=await file.read(10*1024*1024+1)
 if len(data)>10*1024*1024:raise HTTPException(413,"Limite de 10 Mo.")
 os.makedirs("uploads",exist_ok=True);name=uuid.uuid4().hex+"_"+os.path.basename(file.filename or "fichier")
 with open("uploads/"+name,"wb") as f:f.write(data)
 return {"stored":True,"file_id":name,"filename":file.filename,"size":len(data),"warning":"Stockage local de démonstration, non durable sur hébergement multi-instance."}
