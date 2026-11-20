"""P11-b 계정·권한셋·초대 관리 API — 시스템 어드민(require_super) 전용."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import guard, require_super
from app.services import account_service as svc

router = APIRouter(tags=["accounts-admin"])


class PermSetIn(BaseModel):
    name: str
    grants: dict
    memo: str | None = None
    set_id: int | None = None


class AccountIn(BaseModel):
    email: str
    name: str | None = None
    auth_permission_set_id: int | None = None
    is_super: bool = False
    active: bool = True


class InviteIn(BaseModel):
    email: str
    auth_permission_set_id: int


@router.get("/permission-sets")
def list_psets(_: str = Depends(require_super)):
    return svc.list_permission_sets()


@router.post("/permission-sets")
def save_pset(body: PermSetIn, email: str = Depends(require_super)):
    return guard(svc.save_permission_set, body.name, body.grants, email, body.memo, body.set_id)


@router.delete("/permission-sets/{sid}")
def del_pset(sid: int, email: str = Depends(require_super)):
    return guard(svc.delete_permission_set, sid, email)


@router.get("/accounts")
def list_accounts(_: str = Depends(require_super)):
    return svc.list_accounts()


@router.post("/accounts")
def save_account(body: AccountIn, email: str = Depends(require_super)):
    return guard(svc.save_account, body.email, body.name, body.auth_permission_set_id,
                 body.is_super, body.active, email)


@router.get("/invitations")
def list_invites(_: str = Depends(require_super)):
    return svc.list_invitations()


@router.post("/invitations")
def create_invite(body: InviteIn, email: str = Depends(require_super)):
    return guard(svc.create_invitation, body.email, body.auth_permission_set_id, email)


@router.post("/invitations/{iid}/revoke")
def revoke_invite(iid: int, email: str = Depends(require_super)):
    return guard(svc.revoke_invitation, iid, email)


#######################################################################################

SUPER_HTML = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>계정·권한 관리</title><style>
body{font-family:sans-serif;max-width:900px;margin:30px auto}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px}
select,input,button{margin:2px} .ok{color:green}.bad{color:#c00}
</style></head><body>
<h2>계정·권한 관리 (시스템 어드민)</h2>
<p id="me"></p>
<h3>계정</h3>
<table id="accts"><thead><tr><th>이메일</th><th>이름</th><th>권한셋</th><th>시스템어드민</th><th>활성</th><th>마지막 로그인</th></tr></thead><tbody></tbody></table>
<h3>새 계정 / 수정</h3>
<input id="a-email" placeholder="email@domain"><input id="a-name" placeholder="이름">
<select id="a-set"></select>
<label><input type="checkbox" id="a-super"> 시스템 어드민</label>
<label><input type="checkbox" id="a-active" checked> 활성</label>
<button onclick="saveAccount()">저장</button>
<h3>권한셋</h3>
<ul id="psets"></ul>
<h3>초대</h3>
<input id="i-email" placeholder="email@domain"><select id="i-set"></select>
<button onclick="invite()">초대 링크 생성</button>
<ul id="invites"></ul>
<pre id="msg"></pre>
<script>
const me = await (await fetch('/api/me')).json();
document.getElementById('me').textContent = '로그인: ' + me.email + (me.is_super ? ' (시스템 어드민)' : '');
if (!me.is_super) document.body.innerHTML = '<h2>시스템 어드민 전용</h2>';
let SETS = [];
async function load() {
  if (!me.is_super) return;
  const [a, p, inv] = await Promise.all([
    (await fetch('/api/accounts')).json(), (await fetch('/api/permission-sets')).json(),
    (await fetch('/api/invitations')).json()]);
  SETS = p.items.filter(s => !s.deleted_at);
  const so = SETS.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
  document.getElementById('a-set').innerHTML = so;
  document.getElementById('i-set').innerHTML = so;
  document.querySelector('#accts tbody').innerHTML = a.items.map(x => `<tr>
    <td>${x.email}</td><td>${x.name ?? ''}</td><td>${x.set_name ?? (x.is_super ? '—' : '(없음)')}</td>
    <td>${x.is_super ? '★' : ''}</td><td>${x.active ? '활성' : '비활성'}</td><td>${x.last_login_at ?? ''}</td></tr>`).join('');
  document.getElementById('psets').innerHTML = SETS.map(s => `<li>${s.name}${s.builtin ? ' (기본)' : ''}
    <button onclick="delSet(${s.id})">삭제</button></li>`).join('');
  document.getElementById('invites').innerHTML = inv.items.map(i =>
    `<li>${i.email} · ${i.status} · <code>${i.token.slice(0, 10)}…</code>
     ${i.status === '대기' ? `<button onclick="revoke(${i.id})">취소</button>
      <button onclick="navigator.clipboard.writeText(location.origin+'/api/invite/accept?token=${i.token}').then(()=>alert('링크 복사됨'))">링크 복사</button>` : ''}</li>`).join('');
}
async function saveAccount() {
  const r = await fetch('/api/accounts', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email: a-email.value, name: a-name.value || null,
      auth_permission_set_id: a-super.checked ? null : +a-set.value,
      is_super: a-super.checked, active: a-active.checked})});
  document.getElementById('msg').textContent = (await r.json()).detail || '저장됨';
  load();
}
async function delSet(id) { await fetch('/api/permission-sets/'+id, {method:'DELETE'}); load(); }
async function invite() {
  const r = await fetch('/api/invitations', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email: i-email.value, auth_permission_set_id: +i-set.value})});
  const j = await r.json();
  document.getElementById('msg').textContent = j.token
    ? '초대 링크: ' + location.origin + '/api/invite/accept?token=' + j.token
    : (j.detail || '실패');
  load();
}
async function revoke(id) { await fetch('/api/invitations/'+id+'/revoke', {method:'POST'}); load(); }
load();
</script></body></html>"""


@router.get("/super", response_class=HTMLResponse)
async def super_page(request: Request):
    from app.auth import get_current_email, is_admin_email
    from app.services import permission_service
    email = get_current_email(request)
    if not permission_service.is_super(email):
        return HTMLResponse("<h2>시스템 어드민 전용</h2>", status_code=403)
    return HTMLResponse(SUPER_HTML)
