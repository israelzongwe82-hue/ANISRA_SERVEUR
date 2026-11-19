import os, uuid, re, pathlib, mimetypes
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, DateTime, ForeignKey, Text, or_, and_
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt, JWTError

DB=os.getenv('DATABASE_URL','sqlite:///./anisra.db')
if DB.startswith('postgres://'): DB=DB.replace('postgres://','postgresql://',1)
engine=create_engine(DB,connect_args={'check_same_thread':False} if DB.startswith('sqlite') else {},pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,autoflush=False,autocommit=False)
SECRET=os.getenv('ANISRA_SECRET_KEY')
if not SECRET:
    SECRET='DEV_ONLY_CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT'
pwd=CryptContext(schemes=['bcrypt'],deprecated='auto')
oauth=OAuth2PasswordBearer(tokenUrl='/auth/login')
app=FastAPI(title='ANISRA API',version='0.2.0')
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv('CORS_ORIGINS','*').split(',')],allow_credentials=False,allow_methods=['*'],allow_headers=['*'])
UPLOAD_DIR=pathlib.Path(os.getenv('ANISRA_UPLOAD_DIR','uploads')); UPLOAD_DIR.mkdir(parents=True,exist_ok=True)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    username:Mapped[str]=mapped_column(String(32),unique=True,index=True)
    display_name:Mapped[str]=mapped_column(String(80))
    email:Mapped[Optional[str]]=mapped_column(String(254),unique=True,nullable=True,index=True)
    phone:Mapped[Optional[str]]=mapped_column(String(32),unique=True,nullable=True,index=True)
    password_hash:Mapped[str]=mapped_column(String(255))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Contact(Base):
    __tablename__='contacts'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    contact_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
class Invitation(Base):
    __tablename__='invitations'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    sender_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    receiver_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    status:Mapped[str]=mapped_column(String(20),default='pending')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Message(Base):
    __tablename__='messages'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    sender_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    receiver_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    body:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Call(Base):
    __tablename__='calls'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    caller_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    receiver_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    kind:Mapped[str]=mapped_column(String(20),default='vocal')
    status:Mapped[str]=mapped_column(String(20),default='initiated')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
Base.metadata.create_all(engine)

def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
class Register(BaseModel):
    username:str=Field(min_length=3,max_length=32,pattern=r'^[a-zA-Z0-9_.-]+$')
    display_name:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=6,max_length=128)
    email:Optional[EmailStr]=None
    phone:Optional[str]=Field(default=None,max_length=32)
class Login(BaseModel): login:str; password:str
class Invite(BaseModel): receiver_id:str
class Msg(BaseModel): receiver_id:str; body:str=Field(min_length=1,max_length=10000)
class CallIn(BaseModel): receiver_id:str; kind:str='vocal'
class GroupIn(BaseModel): name:str=Field(min_length=1,max_length=100)
class GroupMsg(BaseModel): body:str=Field(min_length=1,max_length=10000)
class Group(Base):
    __tablename__='groups'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    name:Mapped[str]=mapped_column(String(100)); owner_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
class GroupMember(Base):
    __tablename__='group_members'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    group_id:Mapped[str]=mapped_column(ForeignKey('groups.id'),index=True); user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
class GroupMessage(Base):
    __tablename__='group_messages'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    group_id:Mapped[str]=mapped_column(ForeignKey('groups.id'),index=True); sender_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    body:Mapped[str]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
Base.metadata.create_all(engine)

def view(u): return {'id':u.id,'username':u.username,'display_name':u.display_name,'email':u.email,'phone':u.phone}
def make_token(u):
    n=datetime.now(timezone.utc); return jwt.encode({'sub':u.id,'iat':n,'exp':n+timedelta(days=7)},SECRET,algorithm='HS256')
def auth(token:str=Depends(oauth),s:Session=Depends(db)):
    try: uid=jwt.decode(token,SECRET,algorithms=['HS256']).get('sub')
    except JWTError: raise HTTPException(401,'Session invalide ou expirée.')
    u=s.get(User,uid) if uid else None
    if not u: raise HTTPException(401,'Compte introuvable.')
    return u
def is_contact(s,a,b): return bool(s.query(Contact).filter_by(owner_id=a,contact_id=b).first())
def message_view(m): return {'id':m.id,'sender_id':m.sender_id,'receiver_id':m.receiver_id,'body':m.body,'created_at':m.created_at.isoformat()}
def normalize_phone(q): return re.sub(r'[^0-9+]','',q or '')

@app.get('/')
def home(): return {'service':'ANISRA API','status':'online','version':'0.2.0'}
@app.get('/health')
def health(): return {'ok':True}
@app.post('/auth/register')
def register(d:Register,s:Session=Depends(db)):
    if not d.email and not d.phone: raise HTTPException(400,'Ajoutez un e-mail ou un téléphone.')
    if s.query(User).filter(User.username==d.username).first(): raise HTTPException(409,"Nom d'utilisateur déjà utilisé.")
    if d.email and s.query(User).filter(User.email==d.email).first(): raise HTTPException(409,'E-mail déjà utilisé.')
    phone=normalize_phone(d.phone) if d.phone else None
    if phone and s.query(User).filter(User.phone==phone).first(): raise HTTPException(409,'Téléphone déjà utilisé.')
    u=User(username=d.username,display_name=d.display_name,email=d.email,phone=phone,password_hash=pwd.hash(d.password));s.add(u);s.commit();s.refresh(u)
    return {'access_token':make_token(u),'token_type':'bearer','user':view(u)}
@app.post('/auth/login')
def login(d:Login,s:Session=Depends(db)):
    q=d.login.strip(); digits=normalize_phone(q)
    u=s.query(User).filter(or_(User.username==q,User.email==q,User.phone==digits)).first()
    if not u or not pwd.verify(d.password,u.password_hash): raise HTTPException(401,'Identifiants incorrects.')
    return {'access_token':make_token(u),'token_type':'bearer','user':view(u)}
@app.get('/me')
def me(u:User=Depends(auth)): return view(u)
@app.get('/users/search')
def search(q:str=Query(...,min_length=2),s:Session=Depends(db),u:User=Depends(auth)):
    q=q.strip(); digits=normalize_phone(q)
    rows=s.query(User).filter(User.id!=u.id,or_(User.username.ilike(f'%{q}%'),User.display_name.ilike(f'%{q}%'),User.phone.ilike(f'%{digits}%'))).limit(25).all()
    return [view(x) for x in rows]
@app.post('/invitations')
def invite(d:Invite,s:Session=Depends(db),u:User=Depends(auth)):
    if d.receiver_id==u.id or not s.get(User,d.receiver_id): raise HTTPException(404,'Utilisateur introuvable.')
    old=s.query(Invitation).filter_by(sender_id=u.id,receiver_id=d.receiver_id,status='pending').first()
    if old:return {'id':old.id,'status':old.status}
    x=Invitation(sender_id=u.id,receiver_id=d.receiver_id);s.add(x);s.commit();s.refresh(x);return {'id':x.id,'status':x.status}
@app.get('/invitations')
def list_invites(s:Session=Depends(db),u:User=Depends(auth)):
    return [{'id':x.id,'sender_id':x.sender_id,'receiver_id':x.receiver_id,'status':x.status,'created_at':x.created_at.isoformat()} for x in s.query(Invitation).filter(or_(Invitation.sender_id==u.id,Invitation.receiver_id==u.id)).order_by(Invitation.created_at.desc()).limit(100).all()]
@app.post('/invitations/{iid}/{action}')
def answer_invite(iid:str,action:str,s:Session=Depends(db),u:User=Depends(auth)):
    x=s.get(Invitation,iid)
    if not x or x.receiver_id!=u.id: raise HTTPException(404,'Invitation introuvable.')
    if action not in ('accept','decline') or x.status!='pending': raise HTTPException(400,'Action impossible.')
    x.status='accepted' if action=='accept' else 'declined'
    if action=='accept':
        for a,b in ((x.sender_id,x.receiver_id),(x.receiver_id,x.sender_id)):
            if not is_contact(s,a,b): s.add(Contact(owner_id=a,contact_id=b))
    s.commit();return {'status':x.status}
@app.get('/contacts')
def contacts(s:Session=Depends(db),u:User=Depends(auth)):
    ids=[x.contact_id for x in s.query(Contact).filter_by(owner_id=u.id).all()]
    return [view(s.get(User,i)) for i in ids if s.get(User,i)]
@app.delete('/contacts/{contact_id}')
def remove_contact(contact_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    row=s.query(Contact).filter_by(owner_id=u.id,contact_id=contact_id).first()
    if not row: raise HTTPException(404,'Contact introuvable.')
    s.delete(row);s.commit();return {'ok':True,'removed_from_my_contacts':True}
@app.post('/messages')
def send(d:Msg,s:Session=Depends(db),u:User=Depends(auth)):
    if not is_contact(s,u.id,d.receiver_id): raise HTTPException(403,'Vous devez d’abord être contacts.')
    m=Message(sender_id=u.id,receiver_id=d.receiver_id,body=d.body);s.add(m);s.commit();s.refresh(m);return message_view(m)
@app.get('/messages/{other_id}')
def history(other_id:str,s:Session=Depends(db),u:User=Depends(auth),since:str|None=None):
    if not is_contact(s,u.id,other_id): raise HTTPException(403,'Contact non autorisé.')
    q=s.query(Message).filter(or_(and_(Message.sender_id==u.id,Message.receiver_id==other_id),and_(Message.sender_id==other_id,Message.receiver_id==u.id)))
    if since:
        try:q=q.filter(Message.created_at>datetime.fromisoformat(since.replace('Z','+00:00')).replace(tzinfo=None))
        except ValueError: raise HTTPException(400,'Date de synchronisation invalide.')
    return [message_view(m) for m in q.order_by(Message.created_at.asc()).limit(500).all()]
@app.delete('/messages/{message_id}')
def delete_message(message_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    m=s.get(Message,message_id)
    if not m or m.sender_id!=u.id: raise HTTPException(404,'Message introuvable ou non supprimable.')
    s.delete(m);s.commit();return {'ok':True}
@app.delete('/messages/conversation/{other_id}')
def clear_conversation(other_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    rows=s.query(Message).filter(or_(and_(Message.sender_id==u.id,Message.receiver_id==other_id),and_(Message.sender_id==other_id,Message.receiver_id==u.id))).all()
    # Suppression pour cet utilisateur uniquement : on ne retire que ses messages envoyés.
    own=[m for m in rows if m.sender_id==u.id]
    for m in own:s.delete(m)
    s.commit();return {'ok':True,'deleted':len(own)}
@app.post('/calls')
def create_call(d:CallIn,s:Session=Depends(db),u:User=Depends(auth)):
    if not is_contact(s,u.id,d.receiver_id): raise HTTPException(403,'Vous devez être contacts.')
    c=Call(caller_id=u.id,receiver_id=d.receiver_id,kind=d.kind[:20]);s.add(c);s.commit();s.refresh(c)
    return {'id':c.id,'caller_id':c.caller_id,'receiver_id':c.receiver_id,'kind':c.kind,'status':c.status,'created_at':c.created_at.isoformat()}
@app.get('/calls')
def list_calls(s:Session=Depends(db),u:User=Depends(auth)):
    rows=s.query(Call).filter(or_(Call.caller_id==u.id,Call.receiver_id==u.id)).order_by(Call.created_at.desc()).limit(100).all()
    return [{'id':c.id,'caller_id':c.caller_id,'receiver_id':c.receiver_id,'kind':c.kind,'status':c.status,'created_at':c.created_at.isoformat()} for c in rows]
@app.delete('/calls')
def clear_calls(s:Session=Depends(db),u:User=Depends(auth)):
    rows=s.query(Call).filter(or_(Call.caller_id==u.id,Call.receiver_id==u.id)).all()
    for c in rows:s.delete(c)
    s.commit();return {'ok':True,'deleted':len(rows)}
@app.post('/files')
async def upload(file:UploadFile=File(...),u:User=Depends(auth)):
    data=await file.read(15*1024*1024+1)
    if len(data)>15*1024*1024: raise HTTPException(413,'Limite de 15 Mo.')
    name=uuid.uuid4().hex+'_'+pathlib.Path(file.filename or 'fichier').name
    (UPLOAD_DIR/name).write_bytes(data)
    return {'stored':True,'file_id':name,'filename':file.filename,'size':len(data),'url':'files/'+name}
@app.get('/files/{name}')
def download_file(name:str,u:User=Depends(auth)):
    path=(UPLOAD_DIR/name).resolve()
    if path.parent!=UPLOAD_DIR.resolve() or not path.is_file(): raise HTTPException(404,'Fichier introuvable.')
    return FileResponse(path,filename=name.split('_',1)[-1],media_type=mimetypes.guess_type(name)[0] or 'application/octet-stream')
@app.post('/groups')
def create_group(d:GroupIn,s:Session=Depends(db),u:User=Depends(auth)):
    g=Group(name=d.name,owner_id=u.id);s.add(g);s.flush();s.add(GroupMember(group_id=g.id,user_id=u.id));s.commit();s.refresh(g);return {'id':g.id,'name':g.name,'owner_id':u.id}
@app.post('/groups/{gid}/members/{uid}')
def add_member(gid:str,uid:str,s:Session=Depends(db),u:User=Depends(auth)):
    g=s.get(Group,gid)
    if not g or g.owner_id!=u.id: raise HTTPException(403,'Seul le créateur peut ajouter des membres.')
    if not s.get(User,uid): raise HTTPException(404,'Utilisateur introuvable.')
    if not s.query(GroupMember).filter_by(group_id=gid,user_id=uid).first(): s.add(GroupMember(group_id=gid,user_id=uid));s.commit()
    return {'ok':True}
@app.post('/groups/{gid}/messages')
def group_send(gid:str,d:GroupMsg,s:Session=Depends(db),u:User=Depends(auth)):
    if not s.query(GroupMember).filter_by(group_id=gid,user_id=u.id).first(): raise HTTPException(403,'Accès refusé.')
    m=GroupMessage(group_id=gid,sender_id=u.id,body=d.body);s.add(m);s.commit();s.refresh(m);return {'id':m.id,'group_id':gid,'sender_id':u.id,'body':m.body,'created_at':m.created_at.isoformat()}
@app.get('/groups/{gid}/messages')
def group_history(gid:str,s:Session=Depends(db),u:User=Depends(auth)):
    if not s.query(GroupMember).filter_by(group_id=gid,user_id=u.id).first(): raise HTTPException(403,'Accès refusé.')
    return [{'id':m.id,'sender_id':m.sender_id,'body':m.body,'created_at':m.created_at.isoformat()} for m in s.query(GroupMessage).filter_by(group_id=gid).order_by(GroupMessage.created_at.asc()).limit(500).all()]
