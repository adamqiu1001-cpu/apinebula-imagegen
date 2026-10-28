#!/usr/bin/env python3
"""APINebula async image CLI. Python 3.10+, macOS and Windows."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urljoin
from html.parser import HTMLParser
from contextlib import contextmanager
from time import monotonic, sleep

API = "https://apinebula.ai/v1/image-tasks"
CONFIG = Path.home() / ".config" / "codex-imagegen"
KEY_FILE = CONFIG / "apinebula-api-key"
STORAGE_FILE = CONFIG / "apinebula-storage.json"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
IS_WINDOWS = os.name == "nt"


class UserError(Exception):
    """Only deliberately sanitized messages may use this exception."""


def emit(**data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def save(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def private_file(path, content):
    """Apply permissions before writing a secret, including on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise UserError("Secret path must not be a symbolic link")
    temp = path.parent / (".secret-" + uuid.uuid4().hex)
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        if IS_WINDOWS:
            identity = subprocess.check_output(["whoami"], text=True).strip()
            subprocess.run(
                ["icacls", str(temp), "/inheritance:r", "/grant:r", identity + ":(F)"],
                check=True, capture_output=True,
            )
        else:
            os.chmod(temp, 0o600)
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def get_key():
    value = os.environ.get("APINEBULA_API_KEY")
    if not value and KEY_FILE.exists():
        value = KEY_FILE.read_text(encoding="utf-8")
    value = (value or "").strip()
    if not value or any(c.isspace() for c in value):
        raise UserError("API key missing or invalid; run configure-key in your terminal")
    return value


def https_url(value):
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise UserError("An absolute HTTPS URL without embedded credentials is required")
    return value


def session(direct=False):
    import requests
    s = requests.Session()
    s.trust_env = not direct
    # Retain proxy/CA environment support without adopting unrelated .netrc credentials.
    s.auth = lambda request: request
    # requests' default adapter does not retry failed POSTs.
    return s


def api_call(method, endpoint, key, direct=False, payload=None):
    with session(direct) as s:
        r = s.request(method, API + endpoint, json=payload,
                      headers={"Authorization": "Bearer " + key},
                      timeout=(15, 90), allow_redirects=False)
        try:
            data = r.json()
        except ValueError:
            raise UserError(f"HTTP {r.status_code}: non-JSON response; outcome may be unknown") from None
        if not 200 <= r.status_code < 300:
            # Do not echo server bodies: they can include prompts, URLs or credentials.
            code = data.get("code") if isinstance(data, dict) else None
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", code):
                code = "api_error"
            raise UserError(f"HTTP {r.status_code}: {code}; check provider task/usage records")
        if not isinstance(data, dict):
            raise UserError("Unexpected response shape; outcome may be unknown")
        return data


def storage():
    if not STORAGE_FILE.exists():
        raise UserError("Local images require private storage: run configure-storage")
    data = json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
    https_url(data["endpoint"])
    return data


def storage_client(config, direct=False):
    import boto3
    from botocore.config import Config
    options = {"signature_version": "s3v4", "retries": {"max_attempts": 1},
               "connect_timeout": 15, "read_timeout": 60,
               "s3": {"addressing_style": "path"}}
    if direct:
        options["proxies"] = {}
    return boto3.client("s3", endpoint_url=config["endpoint"], region_name=config["region"],
                        aws_access_key_id=config["access_key_id"],
                        aws_secret_access_key=config["secret_access_key"],
                        config=Config(**options))


def inspect_image(path):
    from PIL import Image
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise UserError("Image exceeds this helper's 20 MiB limit; resize a copy first")
    with Image.open(path) as im:
        fmt, size = im.format, im.size
        im.verify()
    allowed = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg"),
               "WEBP": ("image/webp", ".webp")}
    if fmt not in allowed:
        raise UserError("Use PNG, JPEG or WebP")
    return allowed[fmt], size


def session_path(explicit=None):
    """Scope selection to this chat, never the newest file across workspaces."""
    if explicit:
        return Path(explicit).resolve()
    thread = os.environ.get("CODEX_THREAD_ID")
    if not thread:
        return None
    name = hashlib.sha256(thread.encode("utf-8")).hexdigest()[:24]
    return Path.cwd() / ".apinebula" / "sessions" / (name + ".json")


def remember_result(path, state):
    selected = state.get("session_file")
    if not selected:
        return
    if not state.get("completed_at"):
        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        save(path, state)
    target = Path(selected)
    old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    if old.get("completed_at", "") > state["completed_at"]:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    save(target, {"latest_state": str(path.resolve()), "completed_at": state["completed_at"]})


def parent_state(args, selected):
    previous = getattr(args, "from_state", None)
    continuing = getattr(args, "continue_latest", False)
    if previous and continuing:
        raise UserError("Choose --continue or --from-state")
    if (previous or continuing) and (args.image or args.image_url):
        raise UserError("Choose an explicit reference or a previous task, not both")
    if continuing:
        if not selected or not selected.exists():
            raise UserError("No completed image selected in this chat; use --from-state for its known task")
        previous = json.loads(selected.read_text(encoding="utf-8")).get("latest_state")
        if not previous:
            raise UserError("This chat has no latest completed task")
    if not previous:
        return None
    path = Path(previous).resolve()
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("phase") != "completed" or not re.fullmatch(r"task_[A-Za-z0-9_-]+", state.get("task_id", "")):
        raise UserError("The selected parent task is not completed")
    return path, state


def parent_image_url(state, key, direct):
    result = api_call("GET", "/" + state["task_id"] + "?detail=true", key, direct)
    items = result.get("detail", {}).get("data", [])
    if result.get("status") != "completed" or len(items) != 1 or not items[0].get("download_url"):
        raise UserError("Parent download URL unavailable; keep its local image and do not silently start a text-only generation")
    return https_url(items[0]["download_url"])


def tmpfiles_direct_url(value):
    u = urlsplit(value)
    if (u.scheme not in ("http", "https") or u.netloc != "tmpfiles.org"
            or u.query or u.fragment
            or not re.fullmatch(r"/(?:dl/)?[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+/[A-Za-z0-9_-]+)?/[A-Za-z0-9_.-]+", u.path)
            or any(part in (".", "..") for part in u.path.split("/"))):
        raise UserError("Unexpected temporary upload URL")
    path = u.path
    # Numeric legacy pages have a deterministic /dl/ counterpart. New opaque
    # page IDs require the download link actually served by the provider.
    if not path.startswith("/dl/") and path.split("/")[1].isdigit():
        path = "/dl" + path
    return "https://tmpfiles.org" + path


class DownloadLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def verify_tmpfiles(client, value, image):
    url = tmpfiles_direct_url(value)
    identity = urlsplit(value).path.removeprefix("/dl/").strip("/").split("/")[-2:]
    for attempt in range(2):
        with client.get(url, stream=True, timeout=(15, 30), allow_redirects=False) as check:
            check.raise_for_status()
            if check.is_redirect:
                raise UserError("Temporary reference redirected unexpectedly")
            body = bytearray()
            for block in check.iter_content(65536):
                body.extend(block)
                if len(body) > MAX_IMAGE_BYTES:
                    raise UserError("Temporary reference exceeds the image limit")
        if hashlib.sha256(body).digest() == hashlib.sha256(image.read_bytes()).digest():
            return url
        if attempt or len(body) > 1024 * 1024:
            break
        parser = DownloadLinks()
        parser.feed(body.decode("utf-8", errors="replace"))
        candidates = []
        for link in parser.links:
            try:
                candidate = tmpfiles_direct_url(urljoin(url, link))
            except (UserError, ValueError):
                continue
            parts = urlsplit(candidate).path.split("/")
            if parts[1] == "dl" and parts[-2:] == identity:
                candidates.append(candidate)
        if not candidates:
            break
        url = candidates[0]
    raise UserError("Temporary URL does not return the original image; no image task submitted")


def upload_tmpfiles(image, mime, ext, direct=False, *, cached=None, checkpoint=None):
    """Reuse a known upload page; verify its bytes before any generation POST."""
    with session(direct) as s:
        if cached:
            value = cached["page"]
            metadata = {"provider": "tmpfiles", "expires_at": cached["expires_at"]}
            if datetime.fromisoformat(metadata["expires_at"]) <= datetime.now(timezone.utc):
                raise UserError("Cached reference expired; no image task submitted")
        else:
            with image.open("rb") as f:
                r = s.post("https://tmpfiles.org/api/v1/upload",
                           files={"file": (uuid.uuid4().hex + ext, f, mime)},
                           data={"expire": "3600"}, timeout=(15, 90), allow_redirects=False)
            r.raise_for_status()
            data = r.json()
            if data.get("status") != "success":
                raise UserError("Temporary upload failed; no image task submitted")
            value = data.get("data", {}).get("url", "")
            tmpfiles_direct_url(value)
            metadata = {"provider": "tmpfiles", "expires_at": (datetime.now(timezone.utc)
                        + timedelta(hours=1)).isoformat()}
            if checkpoint:
                checkpoint({"page": value, "expires_at": metadata["expires_at"]})
        return verify_tmpfiles(s, value, image), metadata


def submit(args):
    # Validate the storage choice before reserving an output directory.
    if getattr(args, "upload_provider", "tmpfiles") == "s3" and args.image:
        storage()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with task_lock(args.out_dir):
        submit_locked(args)


def submit_locked(args):
    key = get_key()
    prompt = args.prompt_file.read_text(encoding="utf-8-sig").strip()
    if not prompt:
        raise UserError("Prompt file is empty")
    urls = [https_url(u) for u in args.image_url]
    images = [(p, inspect_image(p)[0]) for p in args.image]
    provider = getattr(args, "upload_provider", "tmpfiles")
    cfg = storage() if images and provider == "s3" else None
    selected = session_path(getattr(args, "session_file", None))
    parent = parent_state(args, selected)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "state.json"
    state = {"version": 2, "phase": "preparing", "model": args.model, "uploads": []}
    if selected:
        state["session_file"] = str(selected.resolve())
    if parent:
        state["parent_state"] = str(parent[0])
    # Reservation remains after an uncertain failure, preventing duplicate billing.
    with path.open("x", encoding="utf-8") as f:
        json.dump(state, f)
    (args.out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    recovery_path = args.out_dir / "resume.json"
    recovery = {"quality": args.quality, "images": [str(p.resolve()) for p, _ in images],
                "sha256": [hashlib.sha256(p.read_bytes()).hexdigest() for p, _ in images],
                "cached": {}}
    if images and provider == "tmpfiles" and not urls and not parent:
        private_file(recovery_path, json.dumps(recovery))
    if parent:
        urls.append(parent_image_url(parent[1], key, args.direct))
    if images and provider == "tmpfiles":
        state["phase"] = "reference_uploading"
        save(path, state)
        for index, (image, (mime, ext)) in enumerate(images):
            if recovery_path.exists():
                def checkpoint(item, index=index):
                    recovery["cached"][str(index)] = item
                    private_file(recovery_path, json.dumps(recovery))
                url, upload = upload_tmpfiles(image, mime, ext, args.direct, checkpoint=checkpoint)
            else:
                url, upload = upload_tmpfiles(image, mime, ext, args.direct)
            urls.append(url)
            state["uploads"].append(upload)
            save(path, state)
    elif images:
        client = storage_client(cfg, args.direct)
        for image, (mime, ext) in images:
            object_key = "codex-image-reference/" + uuid.uuid4().hex + ext
            upload = {"endpoint": cfg["endpoint"], "bucket": cfg["bucket"], "key": object_key}
            state["uploads"].append(upload)
            save(path, state)
            with image.open("rb") as f:
                client.put_object(Bucket=cfg["bucket"], Key=object_key, Body=f, ContentType=mime)
            url = client.generate_presigned_url("get_object", Params={"Bucket": cfg["bucket"],
                                               "Key": object_key}, ExpiresIn=86400)
            urls.append(https_url(url))
    submit_ready(path, state, prompt, args.quality, urls, key, args.direct)


def submit_ready(path, state, prompt, quality, urls, key, direct):
    payload = {"model": state["model"], "prompt": prompt, "quality": quality,
               "response_format": "url"}
    if urls:
        payload["images"] = [{"image_url": u} for u in urls]
    state["phase"] = "submission_outcome_unknown"
    save(path, state)
    recovery = path.parent / "resume.json"
    if recovery.exists():
        recovery.unlink()
    result = api_call("POST", "/edits" if urls else "/generations", key, direct, payload)
    task = result.get("task_id") or result.get("id")
    if not isinstance(task, str) or not re.fullmatch(r"task_[A-Za-z0-9_-]+", task):
        raise UserError("No valid task ID; keep state and check provider records before resubmitting")
    state.update(task_id=task, phase=result.get("status", "queued"))
    save(path, state)
    emit(task_id=task, status=state["phase"], state_file=str(path.resolve()))


@contextmanager
def task_lock(directory):
    lock = directory / "resume.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise UserError("Submission or recovery already active or interrupted; check that no process is running before removing resume.lock") from None
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink()


def resume(args):
    with task_lock(args.state.parent):
        resume_locked(args)


def resume_locked(args):
    state = json.loads(args.state.read_text(encoding="utf-8"))
    if state.get("task_id") or state.get("phase") not in ("preparing", "reference_uploading"):
        raise UserError("Resume is only for confirmed pre-submission failures; use status for saved tasks")
    recovery_path = args.state.parent / "resume.json"
    if not recovery_path.exists():
        raise UserError("No resumable local-reference checkpoint; retain state and inspect the original failure")
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    images = [Path(p) for p in recovery["images"]]
    if [hashlib.sha256(p.read_bytes()).hexdigest() for p in images] != recovery["sha256"]:
        raise UserError("Reference image changed since original submission")
    urls, uploads = [], []
    for index, image in enumerate(images):
        mime, ext = inspect_image(image)[0]
        def checkpoint(item, index=index):
            recovery["cached"][str(index)] = item
            private_file(recovery_path, json.dumps(recovery))
        url, metadata = upload_tmpfiles(image, mime, ext, args.direct,
                                      cached=recovery["cached"].get(str(index)), checkpoint=checkpoint)
        urls.append(url)
        uploads.append(metadata)
    state["uploads"] = uploads
    save(args.state, state)
    prompt = (args.state.parent / "prompt.txt").read_text(encoding="utf-8")
    submit_ready(args.state, state, prompt, recovery["quality"], urls, get_key(), args.direct)


def download(url, directory, direct=False):
    """No API or storage credentials are sent to the image CDN."""
    from PIL import Image
    temp = directory / "download.part"
    https_url(url)
    with session(direct) as s:
        # Follow HTTPS redirects manually; every hop is validated.
        for _ in range(6):
            r = s.get(url, stream=True, timeout=(15, 90), allow_redirects=False)
            if r.is_redirect:
                from urllib.parse import urljoin
                url = https_url(urljoin(url, r.headers["Location"]))
                r.close()
                continue
            r.raise_for_status()
            with r, temp.open("wb") as f:
                total = 0
                for block in r.iter_content(65536):
                    total += len(block)
                    if total > 100 * 1024 * 1024:
                        raise UserError("Downloaded image exceeds 100 MiB")
                    f.write(block)
            break
        else:
            raise UserError("Too many image redirects")
    with Image.open(temp) as im:
        fmt, size = im.format, im.size
        im.verify()
    ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(fmt)
    if not ext:
        raise UserError("Unexpected image format; inspect download.part")
    output = directory / ("image" + ext)
    if output.exists():
        raise UserError("Output exists; inspect it before replacing")
    temp.replace(output)
    return output, size


def status_once(args):
    state = json.loads(args.state.read_text(encoding="utf-8"))
    task = state.get("task_id", "")
    if not re.fullmatch(r"task_[A-Za-z0-9_-]+", task):
        raise UserError("No task ID saved; inspect provider task/usage records, do not resubmit blindly")
    if state.get("phase") == "completed" and state.get("output"):
        existing = args.state.parent / state["output"]
        if existing.exists():
            inspect_image(existing)
            remember_result(args.state, state)
            emit(status="completed", image=str(existing.resolve()), size=state.get("size"))
            return "completed"
    result = api_call("GET", "/" + task + "?detail=true", get_key(), args.direct)
    state["phase"] = result.get("status", "unknown")
    save(args.state, state)
    if state["phase"] == "completed":
        if state.get("output"):
            existing = args.state.parent / state["output"]
            if existing.exists():
                remember_result(args.state, state)
                emit(status="completed", image=str(existing.resolve()), size=state.get("size"))
                return "completed"
        items = result.get("detail", {}).get("data", [])
        if len(items) != 1 or not items[0].get("download_url"):
            raise UserError("Completed task lacks one download URL; retain ID and query again")
        output, size = download(items[0]["download_url"], args.state.parent, args.direct)
        state.update(output=output.name, size=list(size))
        save(args.state, state)
        remember_result(args.state, state)
        emit(status="completed", image=str(output.resolve()), size=size)
    elif state["phase"] == "failed":
        emit(status="failed", task_id=task, message="Provider reported failure; check its task details. No new request submitted.")
    else:
        emit(status=state["phase"], task_id=task)

    return state["phase"]


def status(args):
    wait = getattr(args, "wait", 0)
    interval = getattr(args, "interval", 10)
    if not 0 <= wait <= 50 or not 5 <= interval <= 30:
        raise UserError("Use --wait 0..50 seconds and --interval 5..30 seconds")
    deadline = monotonic() + wait
    while True:
        phase = status_once(args)
        remaining = deadline - monotonic()
        if phase in ("completed", "failed") or remaining <= 0:
            return
        sleep(min(interval, remaining))


def cleanup(args):
    state = json.loads(args.state.read_text(encoding="utf-8"))
    if state.get("phase") not in ("completed", "failed"):
        raise UserError("Keep references until the task is completed or failed")
    uploads = state.get("uploads", [])
    if not uploads:
        emit(deleted=0)
        return
    temporary = [u for u in uploads if u.get("provider") == "tmpfiles"]
    private = [u for u in uploads if u.get("provider", "s3") == "s3"]
    if len(temporary) + len(private) != len(uploads):
        raise UserError("Unknown upload provider in state")
    if not private:
        emit(deleted=0, temporary_references=len(temporary), message="Temporary files expire automatically; no immediate-delete API is available")
        return
    cfg = storage()
    for item in private:
        if (item["endpoint"], item["bucket"]) != (cfg["endpoint"], cfg["bucket"]):
            raise UserError("Storage configuration differs from this task; clean up in the original bucket")
        if not re.fullmatch(r"codex-image-reference/[0-9a-f]{32}\.(png|jpg|webp)", item["key"]):
            raise UserError("Unexpected object key in state")
    client = storage_client(cfg, args.direct)
    for item in private:
        client.delete_object(Bucket=item["bucket"], Key=item["key"])
    state["uploads"] = temporary
    save(args.state, state)
    emit(deleted=len(private), temporary_references=len(temporary))


def configure_key():
    key = getpass.getpass("APINebula API Key (hidden): ").strip()
    if not key or any(c.isspace() for c in key):
        raise UserError("Empty or malformed key")
    private_file(KEY_FILE, key + "\n")
    emit(configured=True, file=str(KEY_FILE))


def configure_storage():
    cfg = {"endpoint": https_url(input("S3-compatible HTTPS endpoint: ").strip()),
           "region": input("Region (e.g. auto for R2): ").strip(),
           "bucket": input("Private bucket name: ").strip(),
           "access_key_id": getpass.getpass("Storage access key ID (hidden): ").strip(),
           "secret_access_key": getpass.getpass("Storage secret access key (hidden): ").strip()}
    if not all(cfg.values()):
        raise UserError("All storage fields are required")
    private_file(STORAGE_FILE, json.dumps(cfg))
    emit(configured=True, file=str(STORAGE_FILE))


def main_with_args(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("configure-key")
    sub.add_parser("configure-storage")
    s = sub.add_parser("submit")
    s.add_argument("--prompt-file", type=Path, required=True)
    s.add_argument("--out-dir", type=Path, required=True)
    s.add_argument("--model", default="gpt-image-2.5")
    s.add_argument("--quality", choices=["low", "medium", "high", "auto"], default="high")
    s.add_argument("--image", type=Path, action="append", default=[])
    s.add_argument("--image-url", action="append", default=[])
    s.add_argument("--upload-provider", choices=["s3", "tmpfiles"], default="tmpfiles",
                   help="Local reference upload service (default: tmpfiles, expires after 1 hour)")
    previous = s.add_mutually_exclusive_group()
    previous.add_argument("--continue", dest="continue_latest", action="store_true")
    previous.add_argument("--from-state", type=Path)
    s.add_argument("--session-file", type=Path)
    s.add_argument("--direct", action="store_true")
    for name in ("status", "cleanup", "resume"):
        s = sub.add_parser(name)
        s.add_argument("--state", type=Path, required=True)
        s.add_argument("--direct", action="store_true")
        if name == "status":
            s.add_argument("--wait", type=int, default=0, help="Poll for up to 50 seconds; never resubmits")
            s.add_argument("--interval", type=int, default=10)
    args = p.parse_args(argv)
    try:
        if args.command == "configure-key":
            configure_key()
        elif args.command == "configure-storage":
            configure_storage()
        else:
            globals()[args.command](args)
        return 0
    except UserError as exc:
        # Controlled messages contain no provider response bodies or secrets.
        emit(error=str(exc))
        return 1
    except Exception as exc:
        # Network exceptions may embed signed URLs. Report only the class.
        emit(error=type(exc).__name__, message="Operation interrupted. Keep state.json; use status for saved tasks. Check local setup/network; do not blindly submit again.")
        return 1


def main():
    return main_with_args()


if __name__ == "__main__":
    sys.exit(main())
