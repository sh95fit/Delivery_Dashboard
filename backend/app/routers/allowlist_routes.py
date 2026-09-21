from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth import get_current_email, is_admin_email
from app.schemas.allowlist import AddAllowlistRequest
from app.services import allowlist_service

router = APIRouter(tags=["allowlist"])


@router.get("/allowlist")
async def list_allowlist(request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")
    return allowlist_service.list_allowlist()


@router.post("/allowlist")
async def add_allowlist(request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")
    body = AddAllowlistRequest(**(await request.json()))
    allowlist_service.add_allowlist(body.kind, body.value.strip().lower(), email)
    return {"ok": True}


@router.delete("/allowlist/{item_id}")
async def delete_allowlist(item_id: int, request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")
    allowlist_service.delete_allowlist(item_id)
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
    li.textContent=it.kind+': '+it.value+'  ';
    const b=document.createElement('button'); b.textContent='삭제';
    b.onclick=async()=>{ await fetch('/api/allowlist/'+it.id,{method:'DELETE'}); load(); };
    li.appendChild(b); ul.appendChild(li); } }
async function addItem(){ const kind=document.getElementById('kind').value; const value=document.getElementById('value').value;
  await fetch('/api/allowlist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,value})});
  document.getElementById('value').value=''; load(); }
load();
</script></body></html>"""


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    email = get_current_email(request)
    if not is_admin_email(email):
        return HTMLResponse("<h2>관리자 전용</h2>", status_code=403)
    return HTML_ADMIN
