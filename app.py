import os, sqlite3, secrets
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DATABASE_PATH", os.path.join(BASE, "street_e.sqlite3"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=60*60*24*30)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins=None)
FIGHTERS = [
 {"id":"rook","name":"ROOK","hp":160,"power":17,"style":"밸런스"},
 {"id":"blaze","name":"BLAZE","hp":140,"power":23,"style":"강한 공격"},
 {"id":"moss","name":"MOSS","hp":190,"power":13,"style":"높은 체력"},
 {"id":"volt","name":"VOLT","hp":135,"power":16,"style":"빠른 움직임"},
 {"id":"nova","name":"NOVA","hp":150,"power":19,"style":"공격 특화"},
 {"id":"frost","name":"FROST","hp":170,"power":15,"style":"단단한 방어"},
 {"id":"echo","name":"ECHO","hp":155,"power":18,"style":"기동력"}]
rooms, sid_room = {}, {}

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
with db() as c:
 c.execute("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, nickname TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, coins INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, banned INTEGER NOT NULL DEFAULT 0, is_admin INTEGER NOT NULL DEFAULT 0)""")
 c.execute("""CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), item_key TEXT NOT NULL, UNIQUE(user_id,item_key))""")
 admin=os.environ.get("ADMIN_USERNAME","admin").strip()
 password=os.environ.get("ADMIN_PASSWORD","")
 if password:
  row=c.execute("SELECT id FROM users WHERE username=? COLLATE NOCASE",(admin,)).fetchone()
  if row:
   c.execute("UPDATE users SET is_admin=1, password_hash=? WHERE id=?",(generate_password_hash(password),row["id"]))
  else:
   c.execute("INSERT INTO users(username,nickname,password_hash,is_admin) VALUES(?,?,?,1)",(admin,admin,generate_password_hash(password)))

def current_user():
 uid=session.get("uid")
 if not uid: return None
 with db() as c: return c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
def require_login(fn):
 @wraps(fn)
 def wrapped(*a,**k):
  if not current_user(): return redirect(url_for("login"))
  return fn(*a,**k)
 return wrapped
def require_admin(fn):
 @wraps(fn)
 def wrapped(*a,**k):
  u=current_user()
  if not u or not u["is_admin"]: return redirect(url_for("lobby"))
  return fn(*a,**k)
 return wrapped

CSS="""*{box-sizing:border-box}body{margin:0;background:#10110f;color:#f1f0e8;font:16px Arial,'Malgun Gothic',sans-serif}a{color:inherit;text-decoration:none}.top{padding:18px 5%;display:flex;justify-content:space-between;border-bottom:1px solid #383a33;background:#151613}.brand b,.lime{color:#d9ff62}.wrap{max-width:1100px;margin:auto;padding:28px 18px}.auth{max-width:480px;margin:7vh auto;padding:32px;background:#191a17;border:1px solid #383a33}.muted{color:#9b9d92}.panel{background:#191a17;border:1px solid #383a33;padding:18px;margin:14px 0}.btn,button{display:inline-block;padding:11px 15px;border:1px solid #42443a;background:#22231e;color:#f1f0e8;border-radius:4px;cursor:pointer}.primary{background:#d9ff62;color:#17190f;font-weight:bold}.form{display:grid;gap:12px;margin:20px 0}.form label{display:grid;gap:6px}.form input{padding:12px;background:#10110f;color:white;border:1px solid #42443a}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.fighter{padding:15px;background:#20211d;border:1px solid #42443a;color:white;text-align:left}.fighter:focus,.fighter.selected{border-color:#d9ff62}.notice{padding:10px;background:#28291f;margin:10px 0}.health{height:12px;background:#542c2a;margin:8px 0}.health div{height:100%;background:#d9ff62}.logs{white-space:pre-wrap;max-height:180px;overflow:auto;padding:10px;background:#10110f}.row{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #383a33;text-align:left}input[type=number]{width:85px;padding:7px}@media(max-width:600px){.auth{margin:16px;padding:22px}.top{gap:10px;flex-wrap:wrap}.wrap{padding:18px 12px}}"""
def shell(title, body):
 u=current_user()
 nav=(f'<a href="/lobby">로비</a>　<a href="/shop">상점</a>　<a href="/ranking">랭킹</a>　' + (('<a href="/admin">관리자</a>　') if u and u["is_admin"] else '') + (f'{u["nickname"]} · {u["coins"]}C　<a href="/logout">로그아웃</a>' if u else '<a href="/login">로그인</a>　<a href="/signup">회원가입</a>'))
 return f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} — STREET E</title><style>{CSS}</style><script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script><nav class="top"><a class="brand" href="/"><b>STREET</b> E</a><div>{nav}</div></nav>{body}</html>'
def page(title, body): return shell(title,body)
@app.route("/")
def index():
 if current_user(): return redirect(url_for("lobby"))
 return page("홈",'<main class="auth"><p class="lime">COMMUNITY FIGHTING LEAGUE</p><h1>STREET E</h1><p class="muted">친구와 겨루고 승리를 쌓으세요.</p><div class="row"><a class="btn primary" href="/login">로그인</a><a class="btn" href="/signup">회원가입</a></div></main>')
@app.route("/signup",methods=["GET","POST"])
def signup():
 msg=""
 if request.method=="POST":
  un=request.form.get("username","").strip().lower(); nn=request.form.get("nickname","").strip(); pw=request.form.get("password","")
  if len(un)<3 or len(nn)<2 or len(pw)<8: msg="아이디 3자 이상, 닉네임 2자 이상, 비밀번호 8자 이상으로 입력하세요."
  else:
   try:
    with db() as c: c.execute("INSERT INTO users(username,nickname,password_hash) VALUES(?,?,?)",(un,nn,generate_password_hash(pw)))
    return redirect(url_for("login"))
   except sqlite3.IntegrityError: msg="이미 사용 중인 아이디 또는 닉네임입니다."
 return page("회원가입",f'<main class="auth"><h1>계정 만들기</h1><p>{msg}</p><form class="form" method="post"><label>아이디<input name="username" minlength="3" required></label><label>닉네임<input name="nickname" minlength="2" required></label><label>비밀번호 (8자 이상)<input name="password" type="password" minlength="8" required></label><button class="primary">회원가입</button></form><a href="/login">로그인으로</a></main>')
@app.route("/login",methods=["GET","POST"])
def login():
 msg=""
 if request.method=="POST":
  login_name=request.form.get("username","").strip()
  with db() as c:
   u=c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE",(login_name,)).fetchone()
   if not u: u=c.execute("SELECT * FROM users WHERE nickname=? COLLATE NOCASE",(login_name,)).fetchone()
  if not u or not check_password_hash(u["password_hash"],request.form.get("password","")): msg="아이디 또는 비밀번호를 확인하세요."
  elif u["banned"]: msg="이 계정은 이용 정지 상태입니다."
  else:
   session.clear()
   session.permanent=True
   session["uid"]=int(u["id"])
   session.modified=True
   return redirect(url_for("lobby"))
 return page("로그인",f'<main class="auth"><h1>다시 만나서 반가워요.</h1><p>{msg}</p><form class="form" method="post"><label>아이디 또는 닉네임<input name="username" autocomplete="username" required></label><label>비밀번호<input name="password" type="password" autocomplete="current-password" required></label><button class="primary">로그인</button></form><a href="/signup">회원가입</a></main>')
@app.route("/logout")
def logout(): session.clear(); return redirect("/")
@app.route("/lobby")
@require_login
def lobby():
 u=current_user()
 chars=''.join(f'<button class="fighter" onclick="pick(\'{x["id"]}\',this)"><b>{x["name"]}</b><br>{x["style"]}<br>HP {x["hp"]} · 공격 {x["power"]}</button>' for x in FIGHTERS)
 body=r'''<main class="wrap"><p class="lime">STREET E / FIGHT CLUB</p><h1>전투 준비</h1><div class="panel">플레이어 <b>__NICK__</b>　·　코인 <b id="coins">__COINS__</b> C　·　승리 <b>__WINS__</b></div>
<section class="panel"><h2>파이터 선택</h2><div class="grid">__CHARS__</div><div class="row"><button class="primary" onclick="joinQueue()">온라인 1대1 찾기</button><button onclick="practice()">AI 연습</button><button onclick="stopFight()">전투 나가기</button></div><p id="status" class="muted">파이터를 선택하고 전투를 시작하세요.</p></section>
<section id="fightPanel" class="panel" hidden><div class="fight-head"><div><b id="p1">PLAYER</b><div class="health"><div id="bar0" style="width:100%"></div></div><span id="hp0">100</span> HP</div><div class="vs">VS</div><div style="text-align:right"><b id="p2">RIVAL</b><div class="health"><div id="bar1" style="width:100%"></div></div><span id="hp1">100</span> HP</div></div>
<canvas id="arena" width="900" height="420" aria-label="격투 게임 화면"></canvas><div class="controls-note">이동 <b>A / D</b> · 점프 <b>W</b> · 빠른 공격 <b>J</b> · 강공격 <b>K</b> · 필살기 <b>L</b></div><div class="mobile-controls"><button onpointerdown="keys.left=true" onpointerup="keys.left=false" onpointerleave="keys.left=false">◀</button><button onpointerdown="keys.right=true" onpointerup="keys.right=false" onpointerleave="keys.right=false">▶</button><button onpointerdown="jump()">점프</button><button onpointerdown="attack('j')">J 공격</button><button onpointerdown="attack('k')">K 강공격</button><button onpointerdown="attack('l')">필살기</button></div><div id="logs" class="logs">대전 준비 중…</div></section>
<section class="panel"><h2>진행 중인 대전</h2><button onclick="refreshRooms()">목록 새로고침</button><div id="rooms">불러오는 중…</div></section></main>
<style>
#arena{display:block;width:100%;height:auto;max-height:420px;background:#171b20;border:1px solid #454b4f;image-rendering:pixelated;margin-top:14px}
.fight-head{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px}.vs{font-weight:900;color:#d9ff62;font-size:24px}.controls-note{padding:12px;color:#c7c9bf;font-size:14px}.mobile-controls{display:flex;gap:8px;flex-wrap:wrap}.mobile-controls button{touch-action:none;user-select:none}.health{height:13px;background:#63322d;margin:7px 0}.health div{background:#d9ff62;height:100%;transition:width .1s}
@media(max-width:600px){#arena{max-height:none}.controls-note{font-size:12px}}
</style>
<script>
const socket=typeof io==='function'?io():null;
let character='rook',mode='idle',roomId=null,raf=0,lastSend=0,lastAttack=0,aiClock=0;
const keys={left:false,right:false},fighters={};
const canvas=document.getElementById('arena'),ctx=canvas.getContext('2d');
let me={x:170,y:300,vx:0,vy:0,hp:100,face:1,ground:true,anim:0,attack:0,color:'#d9ff62'};
let foe={x:700,y:300,vx:0,vy:0,hp:100,face:-1,ground:true,anim:0,attack:0,color:'#ff6a58'};
const fighterColors={rook:'#d9ff62',blaze:'#ff6a58',moss:'#70cf8b',volt:'#62c8ff',nova:'#d7a2ff',frost:'#c4e8ff',echo:'#ffbd61'};
function pick(id,b){character=id;document.querySelectorAll('.fighter').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');me.color=fighterColors[id]||'#d9ff62'}
function status(t){document.getElementById('status').textContent=t}
function log(t){let e=document.getElementById('logs');e.textContent=(t+'\n'+e.textContent).slice(0,700)}
function showFight(){document.getElementById('fightPanel').hidden=false;cancelAnimationFrame(raf);frame()}
function practice(){mode='practice';roomId=null;me={x:170,y:300,vx:0,vy:0,hp:100,face:1,ground:true,anim:0,attack:0,color:fighterColors[character]||'#d9ff62'};foe={x:700,y:300,vx:0,vy:0,hp:100,face:-1,ground:true,anim:0,attack:0,color:'#ff6a58'};document.getElementById('p1').textContent='YOU';document.getElementById('p2').textContent='CPU';document.getElementById('logs').textContent='훈련 시작!';status('AI 연습 중 · 키보드로 조작하세요');showFight()}
function joinQueue(){if(!socket){status('온라인 연결을 불러오지 못했어요. 새로고침해 주세요.');return}mode='online';status('상대를 찾는 중… 다른 플레이어가 들어오면 바로 시작합니다.');socket.emit('queue_join',{character})}
function stopFight(){mode='idle';roomId=null;cancelAnimationFrame(raf);document.getElementById('fightPanel').hidden=true;status('전투를 나갔습니다.')}
function jump(){if(me.ground){me.vy=-13;me.ground=false}}
function attack(kind){if(mode==='idle'||mode==='spectate'||performance.now()-lastAttack<260)return;lastAttack=performance.now();me.attack=kind==='l'?28:kind==='k'?18:10;me.anim=me.attack;let damage=kind==='l'?25:kind==='k'?15:8;log(kind==='l'?'필살기!':kind==='k'?'강공격!':'빠른 공격!');if(mode==='practice'){if(Math.abs(me.x-foe.x)<125&&Math.abs(me.y-foe.y)<70){foe.hp=Math.max(0,foe.hp-damage);log('AI에게 '+damage+' 피해!')}return}if(mode==='online'&&socket)socket.emit('fighter_hit',{damage,range:Math.abs(me.x-foe.x),height:Math.abs(me.y-foe.y),kind})}
function updateBars(){for(let i=0;i<2;i++){let p=i?foe:me;document.getElementById('hp'+i).textContent=p.hp;document.getElementById('bar'+i).style.width=p.hp+'%'}}
function drawFighter(p,label){ctx.save();ctx.translate(p.x,p.y);ctx.scale(p.face,1);let swing=p.attack>0?Math.min(42,p.attack*1.5):0;ctx.fillStyle='rgba(0,0,0,.32)';ctx.beginPath();ctx.ellipse(0,4,31,8,0,0,Math.PI*2);ctx.fill();ctx.fillStyle=p.color;ctx.fillRect(-17,-65,34,42);ctx.fillStyle='#e6b995';ctx.beginPath();ctx.arc(0,-78,15,0,Math.PI*2);ctx.fill();ctx.fillStyle='#222';ctx.fillRect(4,-82,9,4);ctx.fillStyle=p.color;ctx.fillRect(-15,-24,12,23);ctx.fillRect(4,-24,12,23);ctx.fillStyle='#d4d5d0';ctx.fillRect(-20,-57,12,25);ctx.fillRect(8,-57,12,25);ctx.fillStyle=p.color;ctx.fillRect(12,-55,28+swing,-11);ctx.fillStyle='#fff';ctx.fillRect(30+swing,-66,12,12);ctx.restore();ctx.fillStyle='#f1f0e8';ctx.font='12px Arial';ctx.textAlign='center';ctx.fillText(label,p.x, p.y-102)}
function draw(){ctx.clearRect(0,0,900,420);let g=ctx.createLinearGradient(0,0,0,420);g.addColorStop(0,'#202b37');g.addColorStop(1,'#151719');ctx.fillStyle=g;ctx.fillRect(0,0,900,420);ctx.fillStyle='#29323a';for(let x=0;x<900;x+=60){ctx.fillRect(x,105,2,195);ctx.fillRect(x+10,130,30,3)}ctx.fillStyle='#363a36';ctx.fillRect(0,325,900,95);ctx.strokeStyle='#6a725d';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,325);ctx.lineTo(900,325);ctx.stroke();for(let x=0;x<900;x+=45){ctx.fillStyle='#41463d';ctx.fillRect(x,350,24,2)}drawFighter(me,mode==='practice'?'YOU':'P1');drawFighter(foe,mode==='practice'?'CPU':'P2');if(me.attack>0){ctx.fillStyle='rgba(217,255,98,.22)';ctx.fillRect(me.x+(me.face>0?12:-100),me.y-78,88,50)}}
function frame(){if(mode==='idle')return;const now=performance.now(),dt=1;me.vx=(keys.left?-5:0)+(keys.right?5:0);if(me.x<foe.x)me.face=1;else me.face=-1;if(mode==='practice'){aiClock+=dt;if(Math.abs(foe.x-me.x)>100)foe.x+=(foe.x>me.x?-1:1)*1.15;else if(aiClock%70<2&&Math.random()>.25){me.hp=Math.max(0,me.hp-5);log('AI 반격! -5 HP')}}me.x=Math.max(35,Math.min(865,me.x+me.vx));me.vy+=.65;me.y+=me.vy;if(me.y>=300){me.y=300;me.vy=0;me.ground=true}if(me.attack>0)me.attack=Math.max(0,me.attack-1);if(mode==='practice'){foe.x=Math.max(35,Math.min(865,foe.x));foe.face=foe.x>me.x?-1:1;if(foe.hp<=0){status('연습 승리! 다시 AI 연습을 눌러 재시작할 수 있어요.');mode='idle'}if(me.hp<=0){status('연습 종료! 다시 AI 연습을 눌러 재도전하세요.');mode='idle'}}if(mode==='online'&&socket&&now-lastSend>50){lastSend=now;socket.emit('fighter_state',{x:me.x,y:me.y,face:me.face,color:me.color})}draw();updateBars();if(mode!=='idle')raf=requestAnimationFrame(frame)}
window.addEventListener('keydown',e=>{let k=e.key.toLowerCase();if(['a','d','w','j','k','l',' '].includes(k))e.preventDefault();if(k==='a')keys.left=true;if(k==='d')keys.right=true;if(k==='w')jump();if(k==='j'||k==='k'||k==='l')attack(k)});
window.addEventListener('keyup',e=>{if(e.key.toLowerCase()==='a')keys.left=false;if(e.key.toLowerCase()==='d')keys.right=false});
function refreshRooms(){fetch('/api/rooms').then(r=>r.json()).then(rs=>{let e=document.getElementById('rooms');e.replaceChildren();let live=rs.filter(x=>x.status==='playing');if(!live.length){e.textContent='현재 진행 중인 대전이 없어요.';return}live.forEach(x=>{let b=document.createElement('button');b.textContent='대전 '+x.id+' 관전';b.onclick=()=>socket&&socket.emit('spectate',{room:x.id});e.append(b)})}).catch(()=>{})}
if(socket){socket.on('connect',refreshRooms);socket.on('queue_status',d=>status(d.message));socket.on('match_found',d=>{mode='online';roomId=d.room;me.hp=100;foe.hp=100;me.x=d.index===0?170:700;foe.x=d.index===0?700:170;me.face=me.x<foe.x?1:-1;document.getElementById('p1').textContent=d.players[d.index||0].nickname;document.getElementById('p2').textContent=d.players[(d.index===0?1:0)].nickname;document.getElementById('logs').textContent='대전 시작!';status('대전 시작!');showFight();refreshRooms()});socket.on('fighter_state',d=>{if(mode==='online'){foe.x=d.x;foe.y=d.y;foe.face=d.face;foe.color=d.color||'#ff6a58'}});socket.on('fighter_hit',d=>{if(mode==='online'){me.hp=d.hp;foe.hp=d.oppHp;log(d.line);updateBars();if(d.winner)status(d.winner+' 승리!')}});socket.on('fight_update',d=>{if(mode==='online'){me.hp=d.hp[0];foe.hp=d.hp[1];updateBars()}});socket.on('match_finished',d=>{status(d.message||d.winner+' 승리!');fetch('/api/me').then(r=>r.json()).then(x=>document.getElementById('coins').textContent=x.coins);refreshRooms()});socket.on('spectate_state',d=>{mode='spectate';me.hp=d.hp[0];foe.hp=d.hp[1];document.getElementById('p1').textContent=d.players[0].nickname;document.getElementById('p2').textContent=d.players[1].nickname;status('관전 중');showFight()})}
</script>'''
 body=body.replace('__NICK__',u['nickname']).replace('__COINS__',str(u['coins'])).replace('__WINS__',str(u['wins'])).replace('__CHARS__',chars)
 return page("로비",body)

@app.route("/api/me")
@require_login
def api_me():
 u=current_user(); return jsonify(nickname=u["nickname"],coins=u["coins"],wins=u["wins"])
@app.route("/api/rooms")
@require_login
def api_rooms(): return jsonify([{"id":k,"status":v["status"],"spectators":len(v["spectators"])} for k,v in rooms.items()])
@app.route("/ranking")
def ranking():
 with db() as c: rows=c.execute("SELECT nickname,coins,wins FROM users WHERE banned=0 ORDER BY wins DESC,coins DESC LIMIT 50").fetchall()
 body='<main class="wrap"><h1>랭킹</h1><div class="panel"><table><tr><th>닉네임</th><th>승리</th><th>코인</th></tr>'+''.join(f'<tr><td>{x["nickname"]}</td><td>{x["wins"]}</td><td>{x["coins"]}</td></tr>' for x in rows)+'</table></div></main>'
 return page("랭킹",body)
@app.route("/shop",methods=["GET","POST"])
@require_login
def shop():
 u=current_user(); items=[("red","붉은 글러브",100),("silver","실버 배지",250),("champ","챔피언 프레임",500)]
 if request.method=="POST":
  item=next((x for x in items if x[0]==request.form.get("key")),None)
  if item:
   with db() as c:
    if u["coins"]>=item[2] and not c.execute("SELECT id FROM inventory WHERE user_id=? AND item_key=?",(u["id"],item[0])).fetchone():
     c.execute("UPDATE users SET coins=coins-? WHERE id=?",(item[2],u["id"]));c.execute("INSERT INTO inventory(user_id,item_key) VALUES(?,?)",(u["id"],item[0]))
   return redirect(url_for("shop"))
 body='<main class="wrap"><h1>상점</h1><div class="grid">'+''.join(f'<form class="panel" method="post"><h2>{name}</h2><p>{price} C</p><input type="hidden" name="key" value="{key}"><button>구매</button></form>' for key,name,price in items)+'</div></main>'
 return page("상점",body)
@app.route("/admin",methods=["GET","POST"])
@require_login
@require_admin
def admin():
 if request.method=="POST":
  uid=request.form.get("uid",type=int); action=request.form.get("action"); amount=request.form.get("amount",type=int,default=0)
  with db() as c:
   if action=="coins": c.execute("UPDATE users SET coins=MAX(0,coins+?) WHERE id=? AND is_admin=0",(max(-100000,min(100000,amount)),uid))
   elif action=="wins": c.execute("UPDATE users SET wins=MAX(0,wins+?) WHERE id=? AND is_admin=0",(max(-100000,min(100000,amount)),uid))
   elif action=="ban": c.execute("UPDATE users SET banned=1 WHERE id=? AND is_admin=0",(uid,))
   elif action=="unban": c.execute("UPDATE users SET banned=0 WHERE id=? AND is_admin=0",(uid,))
  return redirect(url_for("admin"))
 with db() as c: rows=c.execute("SELECT id,username,nickname,coins,wins,banned,is_admin FROM users ORDER BY id DESC").fetchall()
 body='<main class="wrap"><h1>관리자 콘솔</h1><div class="panel"><table><tr><th>계정</th><th>코인</th><th>승리</th><th>관리</th></tr>'+''.join(f'<tr><td>{x["username"]} / {x["nickname"]}</td><td>{x["coins"]}</td><td>{x["wins"]}</td><td>'+''.join(f'<form method="post" style="display:inline-block;margin:3px"><input type="hidden" name="uid" value="{x["id"]}"><input type="hidden" name="action" value="{act}"><input name="amount" type="number" value="{val}"><button>{label}</button></form>' for act,val,label in [("coins",50,"코인 ±"),("wins",1,"승리 ±")] if not x["is_admin"])+ (f'<form method="post" style="display:inline-block"><input type="hidden" name="uid" value="{x["id"]}"><input type="hidden" name="action" value="{"unban" if x["banned"] else "ban"}"><button>{"정지 해제" if x["banned"] else "정지"}</button></form>' if not x["is_admin"] else '')+'</td></tr>' for x in rows)+'</table></div></main>'
 return page("관리자",body)

@socketio.on("connect")
def connected():
 u=current_user()
 if not u or u["banned"]: return False
@socketio.on("queue_join")
def queue_join(data):
 u=current_user()
 if not u or u["banned"]: return
 char=str((data or {}).get("character","rook"))
 if char not in [x["id"] for x in FIGHTERS]: char="rook"
 for rid,r in list(rooms.items()):
  if r["status"]=="waiting" and len(r["players"])==1:
   r["players"].append({"sid":request.sid,"uid":u["id"],"nickname":u["nickname"],"character":char});r["status"]="playing";sid_room[request.sid]=rid;sid_room[r["players"][0]["sid"]]=rid;join_room(rid)
   emit("match_found",{"room":rid,"index":1,"players":[{"nickname":p["nickname"],"character":p["character"]} for p in r["players"]]},to=r["players"][1]["sid"]);emit("match_found",{"room":rid,"index":0,"players":[{"nickname":p["nickname"],"character":p["character"]} for p in r["players"]]},to=r["players"][0]["sid"]);emit("fight_update",{"hp":r["hp"],"logs":r["logs"],"turn":0,"winner":None},room=rid);return
 rid=secrets.token_hex(3);rooms[rid]={"players":[{"sid":request.sid,"uid":u["id"],"nickname":u["nickname"],"character":char}],"spectators":[],"status":"waiting","hp":[100,100],"logs":["상대를 기다리는 중..."],"turn":0,"guarding":None};sid_room[request.sid]=rid;join_room(rid);emit("queue_status",{"message":"상대를 찾는 중입니다. 다른 플레이어가 대기열에 들어오면 연결됩니다."})
@socketio.on("spectate")
def spectate(data):
 u=current_user(); rid=str((data or {}).get("room",""));r=rooms.get(rid)
 if u and not u["banned"] and r and r["status"]=="playing":
  r["spectators"].append({"sid":request.sid,"nickname":u["nickname"]});join_room(rid);emit("spectate_state",{"room":rid,"players":[{"nickname":p["nickname"],"character":p["character"]} for p in r["players"]],"hp":r["hp"],"logs":r["logs"]},to=request.sid)
@socketio.on("fight_action")
def fight_action(data):
 rid=sid_room.get(request.sid);r=rooms.get(rid or "")
 if not r or r["status"]!="playing": return
 idx=next((i for i,p in enumerate(r["players"]) if p["sid"]==request.sid),None)
 if idx is None: return
 act=(data or {}).get("action")
 if act not in ("attack","guard"): return
 opp=1-idx;player=r["players"][idx]
 if act=="attack":
  damage=secrets.choice([9,12,14,16,18]);damage=max(3,damage//3) if r["guarding"]==opp else damage
  r["hp"][opp]=max(0,r["hp"][opp]-damage);line=f'{player["nickname"]} 공격! 상대 체력 -{damage}';r["guarding"]=None
 else: r["guarding"]=idx;line=f'{player["nickname"]} 방어 자세'
 r["logs"]=(r["logs"]+[line])[-8:];r["turn"]+=1;winner=None
 if r["hp"][opp]<=0:
  winner=player;r["status"]="finished"
  with db() as c: c.execute("UPDATE users SET wins=wins+1,coins=coins+50 WHERE id=?",(player["uid"],));c.execute("UPDATE users SET coins=coins+10 WHERE id=?",(r["players"][opp]["uid"],))
 emit("fight_update",{"hp":r["hp"],"logs":r["logs"],"turn":r["turn"],"winner":winner["nickname"] if winner else None},room=rid)
 if winner: emit("match_finished",{"winner":winner["nickname"],"reward":50},room=rid)
@socketio.on("fighter_state")
def fighter_state(data):
 rid=sid_room.get(request.sid);r=rooms.get(rid or "")
 if not r or r["status"]!="playing": return
 idx=next((i for i,p in enumerate(r["players"]) if p["sid"]==request.sid),None)
 if idx is None:return
 try:
  x=max(25,min(875,float(data.get("x",100))));y=max(100,min(300,float(data.get("y",300))));face=1 if float(data.get("face",1))>=0 else -1
 except (TypeError,ValueError,AttributeError):return
 other=1-idx
 emit("fighter_state",{"x":x,"y":y,"face":face,"color":str(data.get("color","#ff6a58"))[:20]},to=r["players"][other]["sid"])
@socketio.on("fighter_hit")
def fighter_hit(data):
 rid=sid_room.get(request.sid);r=rooms.get(rid or "")
 if not r or r["status"]!="playing":return
 idx=next((i for i,p in enumerate(r["players"]) if p["sid"]==request.sid),None)
 if idx is None:return
 try:
  damage=max(1,min(30,int(data.get("damage",8))))
  dist=float(data.get("range",999));height=float(data.get("height",999))
 except (TypeError,ValueError,AttributeError):return
 if dist>125 or height>75:return
 opp=1-idx;r["hp"][opp]=max(0,r["hp"][opp]-damage)
 attacker=r["players"][idx];victim=r["players"][opp]
 winner=None
 if r["hp"][opp]<=0:
  winner=attacker;r["status"]="finished"
  with db() as c:
   c.execute("UPDATE users SET wins=wins+1,coins=coins+50 WHERE id=?",(attacker["uid"],))
   c.execute("UPDATE users SET coins=coins+10 WHERE id=?",(victim["uid"],))
 emit("fighter_hit",{"hp":r["hp"][idx],"oppHp":r["hp"][opp],"line":attacker["nickname"]+" 공격! -"+str(damage)+" HP","winner":winner["nickname"] if winner else None},to=attacker["sid"]);emit("fighter_hit",{"hp":r["hp"][opp],"oppHp":r["hp"][idx],"line":attacker["nickname"]+" 공격! -"+str(damage)+" HP","winner":winner["nickname"] if winner else None},to=victim["sid"])
 if winner:emit("match_finished",{"winner":winner["nickname"],"reward":50},room=rid)

@socketio.on("disconnect")
def disconnected():
 rid=sid_room.pop(request.sid,None)
 if not rid or rid not in rooms:return
 r=rooms[rid];r["players"]=[p for p in r["players"] if p["sid"]!=request.sid];r["spectators"]=[p for p in r["spectators"] if p["sid"]!=request.sid]
 if not r["players"]:rooms.pop(rid,None)
 elif r["status"]=="playing":r["status"]="finished";emit("match_finished",{"winner":r["players"][0]["nickname"],"reward":0,"message":"상대 연결이 끊겼어요."},room=rid)
if __name__=="__main__": socketio.run(app,host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
