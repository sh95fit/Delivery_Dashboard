from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy import text
from app.database import rds_ok, get_engine
from app.auth import (
    oauth, is_allowed_email, is_admin_email,
    get_current_email, set_session_cookie,
)

app = FastAPI(title="Delivery Dashboard API", version="0.2.0")


@app.get("/health")
def health():
    return {"status": "ok", "app": "delivery-dashboard", "version": app.version}


@app.get("/health/db")
def health_db():
    db_connected = rds_ok()
    return {"status": "ok" if db_connected else "error", "db": "connected" if db_connected else "disconnected"}


@app.get("/api/auth/login")
async def login(request: Request):
    redirect_uri = "https://dashboard.lunchlab.me/api/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/api/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    if not is_allowed_email(email):
        return JSONResponse(status_code=403, content={"detail": "접근 권한이 없습니다 — 관리자에게 문의하세요"})
    response = RedirectResponse(url="/")
    set_session_cookie(response, email)
    return response


@app.get("/api/auth/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("lunchlab_session")
    return response


@app.get("/api/me")
async def me(request: Request):
    email = get_current_email(request)
    return {"email": email, "is_admin": is_admin_email(email)}


# --- 접근 관리 (관리자 전용) ---
@app.get("/api/allowlist")
async def list_allowlist(request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, kind, value FROM auth_allowlist ORDER BY id")).fetchall()
    return [{"id": r[0], "kind": r[1], "value": r[2]} for r in rows]


@app.post("/api/allowlist")
async def add_allowlist(request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")
    body = await request.json()
    kind = body.get("kind")  # 'email' | 'domain'
    value = (body.get("value") or "").strip().lower()
    if kind not in ("email", "domain") or not value:
        raise HTTPException(status_code=400, detail="kind(email/domain)와 value 필요")
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO auth_allowlist (kind, value, added_by) VALUES (:k, :v, :a) ON CONFLICT DO NOTHING"),
                     {"k": kind, "v": value, "a": email})
        conn.commit()
    return {"ok": True}


@app.delete("/api/allowlist/{item_id}")
async def delete_allowlist(item_id: int, request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM auth_allowlist WHERE id = :i"), {"i": item_id})
        conn.commit()
    return {"ok": True}

HTML_ADMIN = """<!DOCTYPE html><html lang="ko"><body style="font-family:sans-serif;max-width:640px;margin:40px auto">
<h2>접근 관리 (관리자)</h2>
<p id="me"></p>
<form onsubmit="addItem(); return false;">
  유형: <select id="kind"><option value="email">이메일</option><option value="domain">도메인</option></select>
  값: <input id="value" placeholder="kim@lunchlab.me 또는 lunchlab.me">
  <button>추가</button>
</form>
<ul id="list"></ul>
<script>
async function load(){ const r=await fetch('/api/allowlist'); const rows=await r.json();
  document.getElementById('me').textContent='로그인: ' + (await (await fetch('/api/me')).json()).email;
  const ul=document.getElementById('list'); ul.innerHTML='';
  for(const it of rows){ const li=document.createElement('li');
    li.textContent=`${it.kind}: ${it.value}  `;
    const b=document.createElement('button'); b.textContent='삭제';
    b.onclick=async()=>{ await fetch('/api/allowlist/'+it.id,{method:'DELETE'}); load(); };
    li.appendChild(b); ul.appendChild(li); } }
async function addItem(){ const kind=document.getElementById('kind').value; const value=document.getElementById('value').value;
  await fetch('/api/allowlist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,value})});
  document.getElementById('value').value=''; load(); }
load();
</script></body></html>"""

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        return HTMLResponse("<h2>관리자 전용</h2>", status_code=403)
    return HTML_ADMIN
