import os, uuid, re, pathlib, mimetypes
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, DateTime, ForeignKey, Text, or_, and_, inspect, text as sql_text
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
    avatar_data:Mapped[Optional[str]]=mapped_column(Text,nullable=True)
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
class GroupIn(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    description:Optional[str]=Field(default=None,max_length=1000)
class GroupMsg(BaseModel): body:str=Field(min_length=1,max_length=10000)
class Group(Base):
    __tablename__='groups'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    name:Mapped[str]=mapped_column(String(100)); owner_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    description:Mapped[Optional[str]]=mapped_column(Text,nullable=True)
class GroupMember(Base):
    __tablename__='group_members'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    group_id:Mapped[str]=mapped_column(ForeignKey('groups.id'),index=True); user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
class GroupMessage(Base):
    __tablename__='group_messages'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    group_id:Mapped[str]=mapped_column(ForeignKey('groups.id'),index=True); sender_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    body:Mapped[str]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Presence(Base):
    __tablename__='presence'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),primary_key=True)
    last_seen:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    typing_to:Mapped[Optional[str]]=mapped_column(String,nullable=True)
    typing_until:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
class MessageReceipt(Base):
    __tablename__='message_receipts'
    message_id:Mapped[str]=mapped_column(ForeignKey('messages.id'),primary_key=True)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),primary_key=True)
    delivered_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
    read_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
class Status(Base):
    __tablename__='statuses'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid.uuid4()))
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    body:Mapped[str]=mapped_column(Text,default='')
    media_data:Mapped[Optional[str]]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime,index=True)
class StatusLike(Base):
    __tablename__='status_likes'
    status_id:Mapped[str]=mapped_column(ForeignKey('statuses.id',ondelete='CASCADE'),primary_key=True)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),primary_key=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class ProfileUpdate(BaseModel):
    display_name:Optional[str]=Field(default=None,min_length=1,max_length=80)
    avatar_data:Optional[str]=Field(default=None,max_length=500000)
class StatusIn(BaseModel):
    body:str=Field(default='',max_length=1000)
    media_data:Optional[str]=Field(default=None,max_length=1800000)
    duration_hours:int=Field(default=24,ge=1,le=24)
class GroupUpdate(BaseModel):
    name:Optional[str]=Field(default=None,min_length=1,max_length=100)
    description:Optional[str]=Field(default=None,max_length=1000)
class TypingIn(BaseModel):
    is_typing:bool=False
Base.metadata.create_all(engine)
# Migration légère pour les bases existantes.
try:
    with engine.begin() as conn:
        if 'avatar_data' not in {c['name'] for c in inspect(engine).get_columns('users')}:
            conn.execute(sql_text('ALTER TABLE users ADD COLUMN avatar_data TEXT'))
        if 'media_data' not in {c['name'] for c in inspect(engine).get_columns('statuses')}:
            conn.execute(sql_text('ALTER TABLE statuses ADD COLUMN media_data TEXT'))
        if 'description' not in {c['name'] for c in inspect(engine).get_columns('groups')}:
            conn.execute(sql_text('ALTER TABLE groups ADD COLUMN description TEXT'))
except Exception as migration_error:
    print('Migration avatar_data:', migration_error)

def view(u): return {'id':u.id,'username':u.username,'display_name':u.display_name,'email':u.email,'phone':u.phone,'avatar_data':getattr(u,'avatar_data',None)}
def make_token(u):
    n=datetime.now(timezone.utc); return jwt.encode({'sub':u.id,'iat':n,'exp':n+timedelta(days=180)},SECRET,algorithm='HS256')
def auth(token:str=Depends(oauth),s:Session=Depends(db)):
    try: uid=jwt.decode(token,SECRET,algorithms=['HS256']).get('sub')
    except JWTError: raise HTTPException(401,'Session invalide ou expirée.')
    u=s.get(User,uid) if uid else None
    if not u: raise HTTPException(401,'Compte introuvable.')
    return u
def is_contact(s,a,b): return bool(s.query(Contact).filter_by(owner_id=a,contact_id=b).first())
def message_view(m,s=None,viewer=None):
    out={'id':m.id,'sender_id':m.sender_id,'receiver_id':m.receiver_id,'body':m.body,'created_at':m.created_at.isoformat(),'delivered':False,'read':False}
    if s is not None and viewer is not None and m.sender_id==viewer:
        r=s.get(MessageReceipt,(m.id,m.receiver_id))
        out['delivered']=bool(r and r.delivered_at);out['read']=bool(r and r.read_at)
    return out
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
@app.put('/me/profile')
def update_profile(d:ProfileUpdate,s:Session=Depends(db),u:User=Depends(auth)):
    if d.display_name is not None: u.display_name=d.display_name.strip()
    if d.avatar_data is not None:
        if d.avatar_data and not d.avatar_data.startswith('data:image/'): raise HTTPException(400,'Photo invalide.')
        u.avatar_data=d.avatar_data or None
    s.commit();s.refresh(u);return view(u)
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
@app.post('/contacts/{contact_id}')
def add_contact(contact_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    other=s.get(User,contact_id)
    if not other or other.id==u.id: raise HTTPException(404,'Compte ANISRA introuvable.')
    if not is_contact(s,u.id,other.id):
        s.add(Contact(owner_id=u.id,contact_id=other.id));s.commit()
    return {'ok':True,'contact':view(other)}

@app.get('/contacts')
def contacts(s:Session=Depends(db),u:User=Depends(auth)):
    ids=[x.contact_id for x in s.query(Contact).filter_by(owner_id=u.id).all()]
    return [view(s.get(User,i)) for i in ids if s.get(User,i)]
@app.get('/conversations')
def conversations(s:Session=Depends(db),u:User=Depends(auth)):
    peer_ids=set(x.contact_id for x in s.query(Contact).filter_by(owner_id=u.id).all())
    rows=s.query(Message.sender_id,Message.receiver_id).filter(or_(Message.sender_id==u.id,Message.receiver_id==u.id)).all()
    for sender,receiver in rows:
        peer_ids.add(receiver if sender==u.id else sender)
    result=[]
    for peer_id in peer_ids:
        peer=s.get(User,peer_id)
        if not peer: continue
        last=s.query(Message).filter(or_(and_(Message.sender_id==u.id,Message.receiver_id==peer_id),and_(Message.sender_id==peer_id,Message.receiver_id==u.id))).order_by(Message.created_at.desc()).first()
        unread=0
        incoming=s.query(Message).filter_by(sender_id=peer_id,receiver_id=u.id).all()
        for incoming_message in incoming:
            receipt=s.get(MessageReceipt,(incoming_message.id,u.id))
            if not receipt or not receipt.read_at: unread+=1
        result.append({'user':view(peer),'last_message':message_view(last) if last else None,'unread_count':unread})
    result.sort(key=lambda x:(x['last_message'] or {}).get('created_at',''),reverse=True)
    return result

@app.post('/presence/heartbeat')
def presence_heartbeat(s:Session=Depends(db),u:User=Depends(auth)):
    row=s.get(Presence,u.id)
    if not row:
        row=Presence(user_id=u.id,last_seen=datetime.utcnow());s.add(row)
    else:
        row.last_seen=datetime.utcnow()
    s.commit()
    return {'ok':True,'last_seen':row.last_seen.isoformat()}

@app.get('/presence/{other_id}')
def get_presence(other_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    other=s.get(User,other_id)
    if not other: raise HTTPException(404,'Utilisateur introuvable.')
    allowed=is_contact(s,u.id,other_id) or s.query(Message).filter(or_(and_(Message.sender_id==u.id,Message.receiver_id==other_id),and_(Message.sender_id==other_id,Message.receiver_id==u.id))).first() is not None
    if not allowed: raise HTTPException(403,'Présence non disponible pour ce compte.')
    row=s.get(Presence,other_id)
    now=datetime.utcnow()
    online=bool(row and row.last_seen and (now-row.last_seen).total_seconds()<=65)
    typing=bool(row and row.typing_to==u.id and row.typing_until and row.typing_until>now)
    return {'online':online,'typing':typing,'last_seen':row.last_seen.isoformat() if row and row.last_seen else None}

@app.post('/typing/{other_id}')
def set_typing(other_id:str,d:TypingIn,s:Session=Depends(db),u:User=Depends(auth)):
    if not s.get(User,other_id): raise HTTPException(404,'Utilisateur introuvable.')
    row=s.get(Presence,u.id)
    now=datetime.utcnow()
    if not row:
        row=Presence(user_id=u.id,last_seen=now);s.add(row)
    row.last_seen=now
    row.typing_to=other_id if d.is_typing else None
    row.typing_until=(now+timedelta(seconds=8)) if d.is_typing else None
    s.commit()
    return {'ok':True}

@app.delete('/contacts/{contact_id}')
def remove_contact(contact_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    row=s.query(Contact).filter_by(owner_id=u.id,contact_id=contact_id).first()
    if not row: raise HTTPException(404,'Contact introuvable.')
    s.delete(row);s.commit();return {'ok':True,'removed_from_my_contacts':True}
@app.post('/messages')
def send(d:Msg,s:Session=Depends(db),u:User=Depends(auth)):
    receiver=s.get(User,d.receiver_id)
    if not receiver or receiver.id==u.id: raise HTTPException(404,'Compte destinataire introuvable.')
    # Un premier message établit automatiquement le lien dans les contacts des deux comptes.
    if not is_contact(s,u.id,receiver.id): s.add(Contact(owner_id=u.id,contact_id=receiver.id))
    if not is_contact(s,receiver.id,u.id): s.add(Contact(owner_id=receiver.id,contact_id=u.id))
    m=Message(sender_id=u.id,receiver_id=receiver.id,body=d.body);s.add(m);s.commit();s.refresh(m);return message_view(m)
@app.get('/messages/{other_id}')
def history(other_id:str,s:Session=Depends(db),u:User=Depends(auth),since:str|None=None):
    if not s.get(User,other_id): raise HTTPException(404,'Compte ANISRA introuvable.')
    q=s.query(Message).filter(or_(and_(Message.sender_id==u.id,Message.receiver_id==other_id),and_(Message.sender_id==other_id,Message.receiver_id==u.id)))
    if not is_contact(s,u.id,other_id) and not q.first(): raise HTTPException(403,'Cette discussion n’est pas disponible.')
    if since:
        try:q=q.filter(Message.created_at>datetime.fromisoformat(since.replace('Z','+00:00')).replace(tzinfo=None))
        except ValueError: raise HTTPException(400,'Date de synchronisation invalide.')
    return [message_view(m,s,u.id) for m in q.order_by(Message.created_at.asc()).limit(500).all()]
@app.post('/messages/{other_id}/receipt')
def mark_messages_received(other_id:str,state:dict,s:Session=Depends(db),u:User=Depends(auth)):
    level=state.get('state','delivered')
    if level not in ('delivered','read'): raise HTTPException(400,'État de réception invalide.')
    now=datetime.utcnow()
    rows=s.query(Message).filter(Message.sender_id==other_id,Message.receiver_id==u.id).all()
    for m in rows:
        r=s.get(MessageReceipt,(m.id,u.id))
        if not r: r=MessageReceipt(message_id=m.id,user_id=u.id);s.add(r)
        if not r.delivered_at:r.delivered_at=now
        if level=='read':r.read_at=now
    s.commit();return {'ok':True,'count':len(rows),'state':level}

@app.delete('/messages/{message_id}')
def delete_message(message_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    m=s.get(Message,message_id)
    if not m or m.sender_id!=u.id: raise HTTPException(404,'Message introuvable ou non supprimable.')
    s.query(MessageReceipt).filter_by(message_id=m.id).delete();s.delete(m);s.commit();return {'ok':True}
@app.delete('/messages/conversation/{other_id}')
def clear_conversation(other_id:str,s:Session=Depends(db),u:User=Depends(auth)):
    rows=s.query(Message).filter(or_(and_(Message.sender_id==u.id,Message.receiver_id==other_id),and_(Message.sender_id==other_id,Message.receiver_id==u.id))).all()
    # Suppression pour cet utilisateur uniquement : on ne retire que ses messages envoyés.
    own=[m for m in rows if m.sender_id==u.id]
    for m in own:
        s.query(MessageReceipt).filter_by(message_id=m.id).delete();s.delete(m)
    s.commit();return {'ok':True,'deleted':len(own)}
@app.get('/statuses')
def list_statuses(s:Session=Depends(db),u:User=Depends(auth)):
    now=datetime.utcnow()
    s.query(Status).filter(Status.expires_at<=now).delete(synchronize_session=False);s.commit()
    rows=s.query(Status).order_by(Status.created_at.desc()).limit(300).all()
    result=[]
    for x in rows:
        likes=s.query(StatusLike).filter_by(status_id=x.id).count()
        liked=s.get(StatusLike,(x.id,u.id)) is not None
        result.append({'id':x.id,'user_id':x.user_id,'body':x.body,'media_data':x.media_data,'created_at':x.created_at.isoformat(),'expires_at':x.expires_at.isoformat(),'user':view(s.get(User,x.user_id)),'likes_count':likes,'liked_by_me':liked})
    return result
@app.post('/statuses')
def create_status(d:StatusIn,s:Session=Depends(db),u:User=Depends(auth)):
    if not d.body.strip() and not d.media_data: raise HTTPException(400,'Ajoutez un texte ou une photo.')
    if d.media_data and not d.media_data.startswith('data:image/'): raise HTTPException(400,'Photo de statut invalide.')
    now=datetime.utcnow();x=Status(user_id=u.id,body=d.body,media_data=d.media_data,created_at=now,expires_at=now+timedelta(hours=d.duration_hours));s.add(x);s.commit();s.refresh(x)
    return {'id':x.id,'user_id':u.id,'body':x.body,'media_data':x.media_data,'created_at':x.created_at.isoformat(),'expires_at':x.expires_at.isoformat(),'user':view(u)}
@app.post('/statuses/{sid}/like')
def toggle_status_like(sid:str,s:Session=Depends(db),u:User=Depends(auth)):
    x=s.get(Status,sid)
    if not x or x.expires_at<=datetime.utcnow(): raise HTTPException(404,'Statut introuvable ou expiré.')
    existing=s.get(StatusLike,(sid,u.id))
    if existing: s.delete(existing); liked=False
    else: s.add(StatusLike(status_id=sid,user_id=u.id)); liked=True
    s.commit()
    return {'liked':liked,'likes_count':s.query(StatusLike).filter_by(status_id=sid).count()}

@app.delete('/statuses/{sid}')
def delete_status(sid:str,s:Session=Depends(db),u:User=Depends(auth)):
    x=s.get(Status,sid)
    if not x or x.user_id!=u.id: raise HTTPException(404,'Statut introuvable.')
    s.delete(x);s.commit();return {'ok':True}

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
    document_ext={'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.txt','.csv','.rtf','.odt','.ods','.odp'}
    image_ext={'.jpg','.jpeg','.png','.webp','.gif'}
    original=pathlib.Path(file.filename or 'document').name
    ext=pathlib.Path(original).suffix.lower()
    if ext not in document_ext|image_ext: raise HTTPException(415,'ANISRA accepte les photos JPG, PNG, WEBP, GIF et les documents PDF, Word, Excel, PowerPoint ou texte.')
    limit=8*1024*1024 if ext in image_ext else 15*1024*1024
    data=await file.read(limit+1)
    if len(data)>limit: raise HTTPException(413,'Limite de 8 Mo pour une photo et 15 Mo pour un document.')
    if ext in image_ext and not (file.content_type or '').startswith('image/'): raise HTTPException(415,'Le fichier photo doit être une image valide.')
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
    g=Group(name=d.name,description=d.description,owner_id=u.id);s.add(g);s.flush();s.add(GroupMember(group_id=g.id,user_id=u.id));s.commit();s.refresh(g);return {'id':g.id,'name':g.name,'description':g.description,'owner_id':u.id}
@app.patch('/groups/{gid}')
def update_group(gid:str,d:GroupUpdate,s:Session=Depends(db),u:User=Depends(auth)):
    g=s.get(Group,gid)
    if not g or g.owner_id!=u.id: raise HTTPException(403,'Seul un administrateur propriétaire peut modifier ce groupe.')
    if d.name is not None:g.name=d.name.strip()
    if d.description is not None:g.description=d.description.strip()
    s.commit();s.refresh(g);return {'id':g.id,'name':g.name,'description':g.description,'owner_id':g.owner_id}
@app.get('/groups')
def list_groups(s:Session=Depends(db),u:User=Depends(auth)):
    ids=[x.group_id for x in s.query(GroupMember).filter_by(user_id=u.id).all()]
    return [{'id':g.id,'name':g.name,'description':g.description,'owner_id':g.owner_id} for g in s.query(Group).filter(Group.id.in_(ids)).all()]
@app.delete('/groups/{gid}/members/me')
def leave_group(gid:str,s:Session=Depends(db),u:User=Depends(auth)):
    row=s.query(GroupMember).filter_by(group_id=gid,user_id=u.id).first()
    if not row: raise HTTPException(404,'Vous ne faites pas partie de ce groupe.')
    s.delete(row)
    if s.query(GroupMember).filter_by(group_id=gid).count()==0:
        g=s.get(Group,gid)
        if g:s.delete(g)
    s.commit();return {'ok':True}
@app.delete('/groups/{gid}')
def delete_group(gid:str,s:Session=Depends(db),u:User=Depends(auth)):
    g=s.get(Group,gid)
    if not g or g.owner_id!=u.id: raise HTTPException(403,'Seul le créateur peut supprimer ce groupe.')
    s.query(GroupMember).filter_by(group_id=gid).delete();s.query(GroupMessage).filter_by(group_id=gid).delete();s.delete(g);s.commit();return {'ok':True}

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
