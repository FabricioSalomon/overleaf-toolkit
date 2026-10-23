#!/usr/bin/env python3
"""Replica dos projetos Overleaf na pasta projects/.

npm start (seed): projects/ -> Mongo.
Recompile (watch): Mongo -> projects/.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECTS = REPO / "projects"
META_NAME = ".overleaf-id"
COMPILE_DIR_RE = re.compile(r"^([a-f0-9]{24})-([a-f0-9]{24})$")

TEXT_EXTENSIONS = {
    "tex", "latex", "sty", "cls", "bst", "bib", "bibtex", "txt", "tikz",
    "mtx", "rtex", "md", "asy", "lbx", "bbx", "cbx", "m", "lco", "dtx",
    "ins", "ist", "def", "clo", "ldf", "rmd", "qmd", "lua", "py", "gv",
    "mf", "yml", "yaml", "lhs", "lean", "lean4", "hs", "mk", "xmpdata",
    "cfg", "rnw", "ltx", "inc",
}

MONGO_LIST = r"""
function idOf(v) { return v == null ? null : v.toString(); }
function walk(folder, prefix, acc) {
  (folder.docs || []).forEach(d => acc.docs.push({ path: prefix + d.name, id: idOf(d._id), name: d.name }));
  (folder.fileRefs || []).forEach(f => acc.files.push({ path: prefix + f.name, id: idOf(f._id), name: f.name, hash: f.hash || "" }));
  (folder.folders || []).forEach(sub => {
    const p = prefix + sub.name;
    acc.folders.push({ path: p, id: idOf(sub._id), name: sub.name });
    walk(sub, p + "/", acc);
  });
}
const projects = db.projects.find().toArray().map(p => {
  const acc = { docs: [], files: [], folders: [], rootFolderId: null };
  const root = (p.rootFolder || [])[0];
  if (root) {
    acc.rootFolderId = idOf(root._id);
    walk(root, "", acc);
  }
  const lines = {};
  db.docs.find({ project_id: p._id }).forEach(d => { lines[idOf(d._id)] = d.lines || []; });
  return {
    id: idOf(p._id),
    name: p.name,
    trashed: Array.isArray(p.trashed) ? p.trashed.length > 0 : !!p.trashed,
    ownerId: idOf(p.owner_ref),
    rootDocId: idOf(p.rootDoc_id),
    rootFolderId: acc.rootFolderId,
    docs: acc.docs,
    files: acc.files,
    folders: acc.folders,
    lines
  };
});
const users = db.users.find({}, { email: 1, first_name: 1, last_name: 1, isAdmin: 1 }).toArray().map(u => ({
  id: idOf(u._id),
  email: u.email || "",
  first_name: u.first_name || "",
  last_name: u.last_name || "",
  isAdmin: !!u.isAdmin
}));
print("JSON:" + JSON.stringify({ projects, users }));
"""

NODE_FETCH = r"""
import { readFileSync } from "node:fs";
const payload = JSON.parse(readFileSync(0, "utf8"));
const res = await fetch(payload.url, {
  method: payload.method || "GET",
  headers: payload.headers || {},
  body: payload.body == null ? undefined : JSON.stringify(payload.body),
});
const text = await res.text();
process.stdout.write(JSON.stringify({ status: res.status, body: text }));
"""


class ReplicaError(RuntimeError):
    pass


def say(message: str) -> None:
    print(f"==> Replica: {message}", flush=True)


def run(cmd: list[str], *, input_text: str | None = None, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    if input_text is not None and input_bytes is not None:
        raise ReplicaError("entrada duplicada")
    data = input_bytes if input_bytes is not None else (None if input_text is None else input_text.encode())
    return subprocess.run(cmd, input=data, capture_output=True)


def check(cmd: list[str], *, input_text: str | None = None, input_bytes: bytes | None = None) -> str:
    result = run(cmd, input_text=input_text, input_bytes=input_bytes)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise ReplicaError(f"falhou: {' '.join(cmd[:4])}\n{detail}")
    return result.stdout.decode(errors="replace")


def docker_container(*hints: str) -> str:
    names = check(["docker", "ps", "--format", "{{.Names}}"]).split()
    for hint in hints:
        if hint in names:
            return hint
    for hint in hints:
        for name in names:
            if name == hint or name.endswith("_" + hint) or name.endswith(hint):
                return name
    raise ReplicaError(f"container nao encontrado ({', '.join(hints)}). O Overleaf esta no ar?")


def rc_value(key: str, default: str) -> str:
    path = REPO / "config" / "overleaf.rc"
    if not path.is_file():
        return default
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return default


def overleaf_var_dir() -> Path:
    configured = Path(rc_value("OVERLEAF_DATA_PATH", "data/overleaf"))
    base = configured if configured.is_absolute() else REPO / "toolkit" / configured
    nested = base / "data"
    if (nested / "compiles").is_dir() or (nested / "history").is_dir():
        return nested
    return base


def web_base() -> str:
    port = rc_value("OVERLEAF_PORT", "80")
    return f"http://127.0.0.1:{port}"


def load_state() -> dict:
    raw = check(
        [
            "docker", "exec", "-i", docker_container("mongo"),
            "bash", "-c", "cat > /tmp/replica.js && mongosh sharelatex --quiet --norc --file /tmp/replica.js",
        ],
        input_text=MONGO_LIST,
    )
    for line in raw.splitlines():
        marker = line.find("JSON:")
        if marker == -1:
            continue
        return json.loads(line[marker + len("JSON:"):])
    raise ReplicaError("mongosh nao devolveu o JSON dos projetos")


def projects_by_id(state: dict) -> dict[str, dict]:
    return {item["id"]: item for item in state["projects"]}


def choose_user(state: dict, user_id: str | None = None) -> dict | None:
    users = state["users"]
    if user_id:
        for user in users:
            if user["id"] == user_id:
                return user
    admins = [user for user in users if user["isAdmin"]]
    if admins:
        return admins[0]
    return users[0] if users else None


def session_secret() -> str:
    script = r"""
for d in /proc/[0-9]*; do
  envf="$d/environ"
  [ -r "$envf" ] || continue
  secret=$(tr '\0' '\n' < "$envf" | sed -n 's/^CRYPTO_RANDOM=//p' | head -1)
  if [ -n "$secret" ]; then
    printf '%s' "$secret"
    exit 0
  fi
done
exit 1
"""
    raw = check(
        ["docker", "exec", "-u", "www-data", "-i", docker_container("sharelatex"), "bash", "-s"],
        input_text=script,
    )
    if not raw:
        raise ReplicaError("CRYPTO_RANDOM nao encontrado no container do Overleaf")
    return raw


def sign_sid(sid: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), sid.encode(), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode().rstrip("=")
    return "s:" + sid + "." + signature


class Web:
    def __init__(self, user: dict):
        self.user = user
        sid = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        payload = {
            "cookie": {
                "originalMaxAge": 432000000,
                "expires": "2099-01-01T00:00:00.000Z",
                "secure": False,
                "httpOnly": True,
                "path": "/",
                "sameSite": "lax",
            },
            "validationToken": "v1:" + sid[-4:],
            "csrfSecret": uuid.uuid4().hex,
            "passport": {
                "user": {
                    "_id": user["id"],
                    "first_name": user["first_name"],
                    "last_name": user["last_name"],
                    "email": user["email"],
                    "isAdmin": user["isAdmin"],
                }
            },
        }
        check(
            ["docker", "exec", "-i", docker_container("redis"), "redis-cli", "-x", "SET", f"sess:{sid}"],
            input_text=json.dumps(payload),
        )
        token = sign_sid(sid, session_secret())
        self.cookie = "overleaf.sid=" + urllib.parse.quote(token, safe="")
        self.csrf = self._csrf()

    def _csrf(self) -> str:
        status, body = self.request("GET", "/project")
        match = re.search(r'name="ol-csrfToken" content="([^"]+)"', body.decode(errors="replace"))
        if status != 200 or not match:
            raise ReplicaError(f"nao consegui abrir a sessao do Overleaf (HTTP {status})")
        return match.group(1)

    def request(self, method: str, path: str, *, data: bytes | None = None, headers: dict | None = None) -> tuple[int, bytes]:
        hdrs = {"cookie": self.cookie}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(web_base() + path, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def json(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
        data = None if body is None else json.dumps(body).encode()
        headers = {"x-csrf-token": self.csrf, "content-type": "application/json"}
        status, raw = self.request(method, path, data=data, headers=headers)
        if not raw:
            return status, None
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, {"raw": raw.decode(errors="replace")}

    def upload(self, project_id: str, folder_id: str, rel: str, content: bytes) -> None:
        name = Path(rel).name
        boundary = "----replica" + uuid.uuid4().hex
        chunks = []

        def field(key: str, value: str) -> None:
            chunks.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
            )

        field("name", name)
        parent = str(Path(rel).parent)
        if parent not in ("", "."):
            field("relativePath", rel)
        chunks.append(
            (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"qqfile\"; filename=\"{name}\"\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + content
            + b"\r\n"
        )
        chunks.append(f"--{boundary}--\r\n".encode())
        status, raw = self.request(
            "POST",
            f"/Project/{project_id}/upload?folder_id={folder_id}",
            data=b"".join(chunks),
            headers={
                "x-csrf-token": self.csrf,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        if status >= 300:
            raise ReplicaError(f"upload de {rel} falhou (HTTP {status}): {raw[:300]!r}")

    def delete(self, project_id: str, kind: str, entity_id: str) -> None:
        status, raw = self.request(
            "DELETE",
            f"/project/{project_id}/{kind}/{entity_id}",
            headers={"x-csrf-token": self.csrf},
        )
        if status >= 300:
            raise ReplicaError(f"apagar {kind} {entity_id} falhou (HTTP {status}): {raw[:300]!r}")


def updater(method: str, url: str, body: dict | None = None) -> tuple[int, str]:
    payload = {"url": url, "method": method, "body": body, "headers": {"content-type": "application/json"}}
    raw = check(
        ["docker", "exec", "-i", docker_container("sharelatex"), "node", "--input-type=module", "-e", NODE_FETCH],
        input_text=json.dumps(payload),
    )
    parsed = json.loads(raw)
    return parsed["status"], parsed["body"]


def live_lines(project_id: str, doc_id: str, fallback: list[str]) -> list[str]:
    try:
        status, body = updater("GET", f"http://127.0.0.1:3003/project/{project_id}/doc/{doc_id}")
        if status == 200:
            return json.loads(body).get("lines") or []
    except (ReplicaError, json.JSONDecodeError):
        pass
    return fallback


def set_lines(project_id: str, doc_id: str, lines: list[str], user_id: str) -> None:
    sent = lines if lines else [""]
    status, body = updater(
        "POST",
        f"http://127.0.0.1:3003/project/{project_id}/doc/{doc_id}",
        {"lines": sent, "source": "restore", "user_id": user_id},
    )
    if status >= 300:
        raise ReplicaError(f"setDoc {doc_id} falhou (HTTP {status}): {body[:300]}")


def canon(lines: list[str] | None) -> list[str]:
    lines = list(lines or [])
    if lines == [""]:
        return []
    return lines


def is_text(rel: str) -> bool:
    suffix = Path(rel).suffix.lower().lstrip(".")
    return suffix in TEXT_EXTENSIONS


def read_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    if text == "":
        return []
    return text.split("\n")


def lines_bytes(lines: list[str]) -> bytes:
    lines = canon(lines)
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode()


def git_blob_hash(content: bytes) -> str:
    prefix = f"blob {len(content)}\0".encode()
    return hashlib.sha1(prefix + content).hexdigest()


def blob_file(project_id: str, file_hash: str) -> Path | None:
    history = overleaf_var_dir() / "history"
    rev = project_id[::-1]
    project_blob = (
        history / "overleaf-project-blobs" / rev[:3] / rev[3:6] / rev[6:] / file_hash[:2] / file_hash[2:]
    )
    if project_blob.is_file():
        return project_blob
    global_blob = history / "overleaf-global-blobs" / file_hash[:2] / file_hash[2:]
    if global_blob.is_file():
        return global_blob
    return None


def safe_dirname(name: str, project_id: str) -> str:
    cleaned = name.strip().replace("/", "-").replace("\\", "-")
    if cleaned in ("", ".", "..") or cleaned.startswith("."):
        cleaned = "projeto-" + project_id[:8]
    return cleaned


def read_meta(folder: Path) -> dict | None:
    path = folder / META_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_meta(folder: Path, project_id: str, name: str) -> bool:
    payload = json.dumps({"id": project_id, "name": name}, indent=2) + "\n"
    path = folder / META_NAME
    if path.is_file() and path.read_text(encoding="utf-8") == payload:
        return False
    path.write_text(payload, encoding="utf-8")
    return True


def folder_for(project: dict) -> Path:
    PROJECTS.mkdir(parents=True, exist_ok=True)
    for child in PROJECTS.iterdir():
        if not child.is_dir():
            continue
        meta = read_meta(child)
        if meta and meta.get("id") == project["id"]:
            return child
    dest = PROJECTS / safe_dirname(project["name"], project["id"])
    if dest.exists():
        dest = PROJECTS / f"{safe_dirname(project['name'], project['id'])}-{project['id'][:6]}"
    return dest


def place_folder(project: dict) -> Path:
    current = folder_for(project)
    desired_name = safe_dirname(project["name"], project["id"])
    desired = PROJECTS / desired_name
    if current.exists() and current != desired and not desired.exists():
        current.rename(desired)
        return desired
    return current


def project_files(project: dict) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for doc in project["docs"]:
        lines = live_lines(project["id"], doc["id"], project["lines"].get(doc["id"], []))
        files[doc["path"]] = lines_bytes(lines)
    for item in project["files"]:
        blob = blob_file(project["id"], item["hash"])
        if blob is None:
            say(f"blob ausente, pulando {item['path']}")
            continue
        files[item["path"]] = blob.read_bytes()
    return files


def write_tree(folder: Path, files: dict[str, bytes], project: dict) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    changed = 0
    desired = set(files)
    for rel, content in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.read_bytes() == content:
            continue
        path.write_bytes(content)
        changed += 1
    for path in sorted(folder.rglob("*"), reverse=True):
        if not path.is_file():
            continue
        rel = path.relative_to(folder).as_posix()
        if rel == META_NAME or rel.startswith("."):
            continue
        if rel not in desired:
            path.unlink()
            changed += 1
    for path in sorted(folder.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    if write_meta(folder, project["id"], project["name"]):
        changed += 1
    return changed


def export_project(project: dict) -> int:
    if project.get("trashed"):
        say(f"{project['name']} esta na lixeira, nao vou copiar")
        return 0
    folder = place_folder(project)
    changed = write_tree(folder, project_files(project), project)
    rel = folder.relative_to(REPO)
    if changed:
        say(f"{project['name']} gravado em {rel} ({changed} alteracao(oes))")
    else:
        say(f"{project['name']} ja estava igual em {rel}")
    return changed


def export_all() -> int:
    state = load_state()
    total = 0
    found = False
    for project in state["projects"]:
        if project.get("trashed"):
            continue
        found = True
        total += export_project(project)
    if not found:
        say("nenhum projeto no Mongo")
    return total


def local_files(folder: Path) -> dict[str, Path]:
    found = {}
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(folder).as_posix()
        if rel == META_NAME or rel.startswith(".") or "/." in rel:
            continue
        found[rel] = path
    return found


def parent_dirs(paths: list[str]) -> set[str]:
    dirs: set[str] = set()
    for rel in paths:
        parent = str(Path(rel).parent)
        while parent not in ("", "."):
            dirs.add(parent)
            parent = str(Path(parent).parent)
    return dirs


def wait_for_web() -> None:
    deadline = time.time() + 90
    url = web_base() + "/login"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as res:
                if res.status < 500:
                    return
        except urllib.error.HTTPError as err:
            if err.code < 500:
                return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2)
    raise ReplicaError("Overleaf nao respondeu a tempo")


def seed_folder(folder: Path, state: dict) -> int:
    meta = read_meta(folder) or {}
    by_id = projects_by_id(state)
    project = by_id.get(meta.get("id") or "")
    desired_name = meta.get("name") or folder.name
    if project is None:
        for item in state["projects"]:
            if item["name"] == desired_name and not item.get("trashed"):
                project = item
                break
    user = choose_user(state, None if project is None else project["ownerId"])
    if user is None:
        raise ReplicaError("nenhum usuario no Overleaf. Abra http://localhost/launchpad, crie a conta e rode de novo")
    web = Web(user)
    changes = 0
    if project is None:
        status, body = web.json("POST", "/project/new", {"projectName": desired_name})
        if status >= 300 or not body or "project_id" not in body:
            raise ReplicaError(f"nao criei o projeto {desired_name} (HTTP {status}): {body}")
        say(f"projeto criado: {desired_name}")
        state = load_state()
        project = projects_by_id(state)[body["project_id"]]
        changes += 1
    elif project["name"] != desired_name:
        status, _body = web.json("POST", f"/project/{project['id']}/settings", {"name": desired_name})
        if status >= 300:
            raise ReplicaError(f"nao renomeei {project['name']} para {desired_name}")
        project["name"] = desired_name
        changes += 1

    files = local_files(folder)
    wanted_dirs = parent_dirs(list(files))
    mongo_docs = {item["path"]: item for item in project["docs"]}
    mongo_files = {item["path"]: item for item in project["files"]}

    for folder_info in sorted(project["folders"], key=lambda item: len(item["path"]), reverse=True):
        if folder_info["path"] not in wanted_dirs:
            web.delete(project["id"], "folder", folder_info["id"])
            changes += 1
            prefix = folder_info["path"] + "/"
            mongo_docs = {k: v for k, v in mongo_docs.items() if not k.startswith(prefix)}
            mongo_files = {k: v for k, v in mongo_files.items() if not k.startswith(prefix)}

    for rel, doc in list(mongo_docs.items()):
        if rel not in files or not is_text(rel):
            web.delete(project["id"], "doc", doc["id"])
            changes += 1
            mongo_docs.pop(rel, None)
    for rel, item in list(mongo_files.items()):
        if rel not in files or is_text(rel):
            web.delete(project["id"], "file", item["id"])
            changes += 1
            mongo_files.pop(rel, None)

    for rel, path in sorted(files.items()):
        content = path.read_bytes()
        if is_text(rel):
            try:
                desired = canon(read_lines(path))
            except UnicodeDecodeError:
                desired = None
            if desired is None:
                if rel not in mongo_files or git_blob_hash(content) != mongo_files[rel]["hash"]:
                    if rel in mongo_files:
                        web.delete(project["id"], "file", mongo_files[rel]["id"])
                    web.upload(project["id"], project["rootFolderId"], rel, content)
                    changes += 1
                continue
            if rel in mongo_docs:
                current = canon(live_lines(project["id"], mongo_docs[rel]["id"], project["lines"].get(mongo_docs[rel]["id"], [])))
                if current != desired:
                    set_lines(project["id"], mongo_docs[rel]["id"], desired, project["ownerId"])
                    changes += 1
            else:
                web.upload(project["id"], project["rootFolderId"], rel, content)
                changes += 1
        else:
            digest = git_blob_hash(content)
            if rel in mongo_files and mongo_files[rel]["hash"] == digest:
                continue
            if rel in mongo_files:
                web.delete(project["id"], "file", mongo_files[rel]["id"])
            web.upload(project["id"], project["rootFolderId"], rel, content)
            changes += 1

    state = load_state()
    project = projects_by_id(state)[project["id"]]
    main = next((doc for doc in project["docs"] if doc["path"] == "main.tex"), None)
    if main and project.get("rootDocId") != main["id"]:
        status, _body = web.json("POST", f"/project/{project['id']}/settings", {"rootDocId": main["id"]})
        if status >= 300:
            raise ReplicaError("nao consegui marcar main.tex como documento raiz")
        changes += 1
    write_meta(folder, project["id"], project["name"])
    if changes:
        say(f"{project['name']} aplicado no Mongo ({changes} alteracao(oes))")
    else:
        say(f"{project['name']} ja estava igual no Mongo")
    return changes


def seed() -> int:
    if not PROJECTS.is_dir():
        say("projects/ ainda nao existe, Mongo permanece como esta")
        return 0
    folders = sorted(path for path in PROJECTS.iterdir() if path.is_dir() and not path.name.startswith("."))
    if not folders:
        say("projects/ vazio, Mongo permanece como esta")
        return 0
    wait_for_web()
    state = load_state()
    if not state["users"]:
        say("nenhum usuario ainda. Abra http://localhost/launchpad, crie a conta e rode npm start de novo")
        return 0
    total = 0
    for folder in folders:
        total += seed_folder(folder, state)
        state = load_state()
    return total


def compile_dirs() -> dict[str, int]:
    root = overleaf_var_dir() / "compiles"
    found: dict[str, int] = {}
    if not root.is_dir():
        return found
    for child in root.iterdir():
        match = COMPILE_DIR_RE.match(child.name)
        if not match or not child.is_dir():
            continue
        log = child / "output.log"
        if not log.is_file():
            continue
        project_id = match.group(1)
        found[project_id] = max(found.get(project_id, 0), log.stat().st_mtime_ns)
    return found


def watch() -> None:
    say("observando recompiles. Cada Recompile atualiza projects/")
    seen = compile_dirs()
    while True:
        time.sleep(2)
        current = compile_dirs()
        for project_id, mtime in current.items():
            if seen.get(project_id) == mtime:
                continue
            time.sleep(1.5)
            stable = compile_dirs().get(project_id)
            if stable != mtime:
                continue
            seen[project_id] = stable
            try:
                state = load_state()
                project = projects_by_id(state).get(project_id)
                if project is None:
                    say(f"recompile de projeto desconhecido {project_id}")
                    continue
                say(f"recompile de {project['name']}")
                export_project(project)
            except ReplicaError as err:
                print(f"erro: {err}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replica projects/ <-> Overleaf")
    parser.add_argument("command", choices=("seed", "export", "watch"))
    args = parser.parse_args()
    try:
        if args.command == "seed":
            seed()
        elif args.command == "export":
            export_all()
        else:
            watch()
    except ReplicaError as err:
        print(f"erro: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
