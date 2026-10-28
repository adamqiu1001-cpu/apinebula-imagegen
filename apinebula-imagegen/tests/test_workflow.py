"""Offline tests: no paid generation, private storage or real keys required."""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image

SPEC = importlib.util.spec_from_file_location("apinebula_image", Path(__file__).parents[1] / "scripts/apinebula_image.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nebula 中文 空格 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prompt = self.root / "提示词.txt"
        self.prompt.write_text("雨夜城市", encoding="utf-8")
        self.args = argparse.Namespace(prompt_file=self.prompt, out_dir=self.root / "输出", image=[],
                                       image_url=[], model="gpt-image-2.5", quality="high", direct=False, session_file=self.root / "session.json")
        self.key = patch.object(m, "get_key", return_value="test-key-never-log")
        self.key.start()
        self.addCleanup(self.key.stop)

    def create(self, result=None):
        with patch.object(m, "api_call", return_value=result or {"id": "task_test", "status": "queued"}) as call:
            m.submit(self.args)
            return call

    def state_args(self):
        return argparse.Namespace(state=self.args.out_dir / "state.json", direct=False)


class WorkflowTests(WorkflowCase):
    def test_text_submission_and_duplicate_guard(self):
        call = self.create()
        self.assertEqual(call.call_args.args[1], "/generations")
        payload = call.call_args.args[4]
        self.assertEqual(payload["prompt"], "雨夜城市")
        self.assertNotIn("images", payload)
        with patch.object(m, "api_call") as again:
            with self.assertRaises(FileExistsError):
                m.submit(self.args)
            again.assert_not_called()

    def test_url_reference_uses_edits(self):
        self.args.image_url = ["https://example.com/reference.png"]
        call = self.create()
        self.assertEqual(call.call_args.args[1], "/edits")
        self.assertEqual(call.call_args.args[4]["images"][0]["image_url"], self.args.image_url[0])

    def test_local_reference_upload_and_sign_before_submit(self):
        image = self.root / "本地 图.png"
        Image.new("RGB", (16, 16), "blue").save(image)
        self.args.image = [image]
        self.args.upload_provider = "s3"
        cfg = {"endpoint": "https://storage.example.com", "bucket": "private"}
        client = MagicMock()
        client.generate_presigned_url.return_value = "https://storage.example.com/ref.png?signature=secret"
        with patch.object(m, "storage", return_value=cfg), patch.object(m, "storage_client", return_value=client):
            call = self.create()
        client.put_object.assert_called_once()
        self.assertEqual(client.generate_presigned_url.call_args.kwargs["ExpiresIn"], 86400)
        self.assertEqual(call.call_args.args[1], "/edits")
        self.assertIn("signature=secret", call.call_args.args[4]["images"][0]["image_url"])
        state = self.state_args().state.read_text()
        self.assertNotIn("signature", state)
        self.assertNotIn("test-key", state)

    def test_missing_storage_stops_before_submission(self):
        image = self.root / "ref.png"
        Image.new("RGB", (8, 8)).save(image)
        self.args.image = [image]
        self.args.upload_provider = "s3"
        with patch.object(m, "STORAGE_FILE", self.root / "missing.json"), patch.object(m, "api_call") as call:
            with self.assertRaises(m.UserError):
                m.submit(self.args)
            call.assert_not_called()
        self.assertFalse(self.args.out_dir.exists())

    def test_uncertain_submission_is_retained_without_retry(self):
        with patch.object(m, "api_call", side_effect=ConnectionError("test")) as call:
            with self.assertRaises(ConnectionError):
                m.submit(self.args)
            self.assertEqual(call.call_count, 1)
        state = json.loads(self.state_args().state.read_text())
        self.assertEqual(state["phase"], "submission_outcome_unknown")
        with patch.object(m, "api_call") as call:
            with self.assertRaises(m.UserError):
                m.status(self.state_args())
            call.assert_not_called()

    def test_status_recovers_and_downloads_once(self):
        self.create()
        result = {"status": "completed", "detail": {"data": [{"download_url": "https://cdn.example.com/out.png"}]}}
        output = self.args.out_dir / "image.png"

        def downloaded(*args):
            Image.new("RGB", (20, 20)).save(output)
            return output, (20, 20)

        with patch.object(m, "api_call", return_value=result) as call, patch.object(m, "download", side_effect=downloaded) as dl:
            m.status(self.state_args())
            m.status(self.state_args())
            self.assertTrue(all(c.args[0] == "GET" for c in call.call_args_list))
            self.assertEqual(dl.call_count, 1)

    def test_failed_task_does_not_resubmit(self):
        self.create()
        with patch.object(m, "api_call", return_value={"status": "failed"}) as call, patch.object(m, "download") as dl:
            m.status(self.state_args())
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[0], "GET")
            dl.assert_not_called()

    def test_download_retry_reuses_task(self):
        self.create()
        result = {"status": "completed", "detail": {"data": [{"download_url": "https://cdn.example.com/out.png"}]}}
        with patch.object(m, "api_call", return_value=result), patch.object(m, "download", side_effect=ConnectionError):
            with self.assertRaises(ConnectionError):
                m.status(self.state_args())
        self.assertEqual(json.loads(self.state_args().state.read_text())["task_id"], "task_test")

    def test_invalid_reference_urls_rejected(self):
        for url in ("data:image/png;base64,eA==", "file:///tmp/a.png", "http://example.com/a.png", "https://user:secret@example.com/a"):
            with self.subTest(url=url), self.assertRaises(m.UserError):
                m.https_url(url)

    def test_download_validates_real_image_and_does_not_send_auth(self):
        b = io.BytesIO()
        Image.new("RGB", (12, 15)).save(b, format="PNG")
        r = MagicMock()
        r.is_redirect = False
        r.iter_content.return_value = [b.getvalue()]
        s = MagicMock()
        s.get.return_value = r
        with patch.object(m, "session") as factory:
            factory.return_value.__enter__.return_value = s
            output, size = m.download("https://cdn.example.com/image", self.root)
        self.assertEqual(size, (12, 15))
        self.assertEqual(output.suffix, ".png")
        self.assertNotIn("headers", s.get.call_args.kwargs)

    def test_corrupt_download_not_promoted_to_final(self):
        r = MagicMock()
        r.is_redirect = False
        r.iter_content.return_value = [b"not an image"]
        with patch.object(m, "session") as factory:
            factory.return_value.__enter__.return_value.get.return_value = r
            with self.assertRaises(Exception):
                m.download("https://cdn.example.com/image", self.root)
        self.assertFalse((self.root / "image.png").exists())

    @unittest.skipIf(m.IS_WINDOWS, "POSIX mode bits do not represent Windows ACLs")
    def test_private_file_posix_mode(self):
        path = self.root / "key"
        with patch.object(m, "IS_WINDOWS", False):
            m.private_file(path, "test-secret")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_windows_acl_before_secret_write(self):
        path = self.root / "key"

        def acl(args, **kwargs):
            self.assertEqual(Path(args[1]).read_bytes(), b"")
            self.assertIn("/inheritance:r", args)
            self.assertIn("DOMAIN\\tester:(F)", args)

        with patch.object(m, "IS_WINDOWS", True), patch.object(m.subprocess, "check_output", return_value="DOMAIN\\tester\n"), patch.object(m.subprocess, "run", side_effect=acl):
            m.private_file(path, "test-secret")
        self.assertEqual(path.read_text(), "test-secret")

    def test_windows_acl_failure_writes_no_secret(self):
        path = self.root / "key"
        with patch.object(m, "IS_WINDOWS", True), patch.object(m.subprocess, "check_output", return_value="tester\n"), patch.object(m.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "icacls")):
            with self.assertRaises(subprocess.CalledProcessError):
                m.private_file(path, "test-secret")
        self.assertFalse(path.exists())
        self.assertFalse(list(self.root.glob(".secret-*")))

    def test_cleanup_restricted_to_recorded_terminal_task(self):
        self.create()
        args = self.state_args()
        with self.assertRaises(m.UserError):
            m.cleanup(args)
        state = json.loads(args.state.read_text())
        state.update(phase="completed", uploads=[{"endpoint": "https://store.example.com", "bucket": "b", "key": "codex-image-reference/" + "a" * 32 + ".png"}])
        m.save(args.state, state)
        client = MagicMock()
        with patch.object(m, "storage", return_value={"endpoint": "https://store.example.com", "bucket": "b"}), patch.object(m, "storage_client", return_value=client):
            m.cleanup(args)
        client.delete_object.assert_called_once()
        self.assertEqual(json.loads(args.state.read_text())["uploads"], [])


class ContinuationTests(WorkflowCase):
    def completed_parent(self):
        self.create()
        output = self.args.out_dir / "image.png"
        Image.new("RGB", (20, 20), "blue").save(output)
        state = json.loads(self.state_args().state.read_text())
        state.update(phase="completed", output="image.png", size=[20, 20])
        m.save(self.state_args().state, state)
        return self.state_args().state

    def test_continue_reuses_parent_url_without_local_upload(self):
        parent = self.completed_parent()
        self.args.from_state = parent
        self.args.out_dir = self.root / "second"
        requests = []
        def api(method, endpoint, key, direct=False, payload=None):
            requests.append((method, endpoint, payload))
            if method == "GET":
                return {"status": "completed", "detail": {"data": [{"download_url": "https://cdn.example.com/fresh.png?token=private"}]}}
            return {"id": "task_second", "status": "queued"}
        with patch.object(m, "api_call", side_effect=api):
            m.submit(self.args)
        self.assertEqual([x[0] for x in requests], ["GET", "POST"])
        self.assertEqual(requests[-1][1], "/edits")
        self.assertEqual(requests[-1][2]["images"], [{"image_url": "https://cdn.example.com/fresh.png?token=private"}])
        state = json.loads((self.args.out_dir / "state.json").read_text())
        self.assertEqual(Path(state["parent_state"]), parent.resolve())
        self.assertNotIn("token=private", json.dumps(state))

    def test_only_downloaded_success_becomes_latest(self):
        self.create()
        sessionfile = self.args.session_file
        self.assertFalse(sessionfile.exists())
        output = self.args.out_dir / "image.png"
        def downloaded(*args):
            Image.new("RGB", (20, 20)).save(output)
            return output, (20, 20)
        response = {"status": "completed", "detail": {"data": [{"download_url": "https://cdn.example.com/out.png"}]}}
        with patch.object(m, "api_call", return_value=response), patch.object(m, "download", side_effect=downloaded):
            m.status(self.state_args())
        selected = json.loads(sessionfile.read_text())
        self.assertEqual(Path(selected["latest_state"]), self.state_args().state.resolve())
        self.args.out_dir = self.root / "failed-later"
        self.create({"id": "task_failed", "status": "queued"})
        with patch.object(m, "api_call", return_value={"status": "failed"}):
            m.status(self.state_args())
        self.assertEqual(json.loads(sessionfile.read_text()), selected)

    def test_continue_uses_session_selection_and_fails_if_missing(self):
        self.args.continue_latest = True
        with self.assertRaises(m.UserError), patch.object(m, "api_call") as api:
            m.submit(self.args)
        api.assert_not_called()
        self.args.continue_latest = False
        parent = self.completed_parent()
        self.args.continue_latest = True
        m.save(self.args.session_file, {"latest_state": str(parent.resolve())})
        self.args.out_dir = self.root / "continued"
        def api(method, endpoint, key, direct=False, payload=None):
            if method == "GET":
                return {"status": "completed", "detail": {"data": [{"download_url": "https://cdn.example.com/current.png"}]}}
            return {"id": "task_continued", "status": "queued"}
        with patch.object(m, "api_call", side_effect=api):
            m.submit(self.args)
        self.assertEqual(json.loads((self.args.out_dir / "state.json").read_text())["parent_state"], str(parent.resolve()))

    def test_chat_sessions_do_not_share_latest(self):
        with patch.dict(m.os.environ, {"CODEX_THREAD_ID": "chat-a"}):
            a = m.session_path()
        with patch.dict(m.os.environ, {"CODEX_THREAD_ID": "chat-b"}):
            b = m.session_path()
        self.assertNotEqual(a, b)
        with patch.dict(m.os.environ, {}, clear=True):
            self.assertIsNone(m.session_path())

    def test_duplicate_continuation_stops_before_network(self):
        parent = self.completed_parent()
        self.args.from_state = parent
        with patch.object(m, "api_call") as api, self.assertRaises(FileExistsError):
            m.submit(self.args)
        api.assert_not_called()

    def test_rechecking_older_success_does_not_replace_newer_selection(self):
        parent = self.completed_parent()
        state = json.loads(parent.read_text())
        state["completed_at"] = "2026-10-27T10:00:00+00:00"
        m.save(parent, state)
        selection = {"latest_state": str(self.root / "newer/state.json"), "completed_at": "2026-10-27T11:00:00+00:00"}
        m.save(self.args.session_file, selection)
        m.remember_result(parent, state)
        self.assertEqual(json.loads(self.args.session_file.read_text()), selection)

    def test_unavailable_parent_does_not_submit_paid_request(self):
        parent = self.completed_parent()
        self.args.from_state = parent
        self.args.out_dir = self.root / "retry-edit"
        with patch.object(m, "api_call", return_value={"status": "completed", "detail": {"data": []}}) as api:
            with self.assertRaises(m.UserError):
                m.submit(self.args)
        self.assertEqual([c.args[0] for c in api.call_args_list], ["GET"])


class TemporaryUploadTests(WorkflowCase):
    def run_upload(self, body=None):
        image = self.root / "ref.png"
        Image.new("RGB", (8, 8), "blue").save(image)
        uploaded, checked, client = MagicMock(), MagicMock(), MagicMock()
        uploaded.json.return_value = {"status": "success", "data": {"url": "https://tmpfiles.org/dl/42/ref.png"}}
        checked.is_redirect = False
        checked.iter_content.return_value = [image.read_bytes() if body is None else body]
        checked.__enter__.return_value = checked
        client.post.return_value = uploaded
        client.get.return_value = checked
        with patch.object(m, "session") as factory:
            factory.return_value.__enter__.return_value = client
            result = m.upload_tmpfiles(image, "image/png", ".png")
        return result, client

    def test_temporary_reference_verifies_bytes_and_sets_expiry_without_auth(self):
        (url, metadata), client = self.run_upload()
        self.assertEqual(url, "https://tmpfiles.org/dl/42/ref.png")
        self.assertEqual(metadata["provider"], "tmpfiles")
        from datetime import datetime, timezone
        remaining = (datetime.fromisoformat(metadata["expires_at"]) - datetime.now(timezone.utc)).total_seconds()
        self.assertTrue(3500 < remaining <= 3600)
        self.assertEqual(client.post.call_args.kwargs["data"], {"expire": "3600"})
        self.assertNotIn("headers", client.post.call_args.kwargs)
        self.assertNotIn("headers", client.get.call_args.kwargs)
        self.assertNotIn("url", metadata)

    def test_html_preview_never_becomes_reference(self):
        with self.assertRaises(m.UserError):
            self.run_upload(b"<html>Preview, not original image</html>")

    def test_local_reference_defaults_to_tmpfiles_without_storage(self):
        image = self.root / "ref.png"
        Image.new("RGB", (8, 8), "blue").save(image)
        self.args.image = [image]
        with patch.object(m, "storage", side_effect=AssertionError("Default must not require S3")), patch.object(m, "upload_tmpfiles", return_value=("https://tmpfiles.org/dl/42/ref.png", {"provider": "tmpfiles", "expires_at": "2026-10-27T12:00:00+00:00"}), create=True):
            call = self.create()
        self.assertEqual(call.call_args.args[4]["images"], [{"image_url": "https://tmpfiles.org/dl/42/ref.png"}])
        state = json.loads(self.state_args().state.read_text())
        self.assertEqual(state["uploads"][0]["provider"], "tmpfiles")

    def test_cli_local_image_defaults_to_tmpfiles_and_allows_s3_override(self):
        for extra, expected in (([], "tmpfiles"), (["--upload-provider", "s3"], "s3")):
            with self.subTest(provider=expected), patch.object(m.sys, "argv", ["apinebula_image.py", "submit", "--prompt-file", str(self.prompt), "--out-dir", str(self.root / "cli"), "--image", "ref.png"] + extra), patch.object(m, "submit") as submit:
                self.assertEqual(m.main(), 0)
                self.assertEqual(submit.call_args.args[0].upload_provider, expected)

    def test_tmpfiles_response_must_point_to_provider(self):
        for bad in ("https://evil.example/42/ref.png", "https://user:secret@tmpfiles.org/42/ref.png", "https://tmpfiles.org/", "https://tmpfiles.org/42/ref.png?secret=x"):
            with self.subTest(url=bad), self.assertRaises(m.UserError):
                m.tmpfiles_direct_url(bad)
        self.assertEqual(m.tmpfiles_direct_url("http://tmpfiles.org/42/ref.png"), "https://tmpfiles.org/dl/42/ref.png")
        self.assertEqual(m.tmpfiles_direct_url("https://tmpfiles.org/dl/1793100000.sigN_12/token12/ref.png"), "https://tmpfiles.org/dl/1793100000.sigN_12/token12/ref.png")
        self.assertEqual(m.tmpfiles_direct_url("https://tmpfiles.org/dl/42/ref.png"), "https://tmpfiles.org/dl/42/ref.png")

    def test_upload_failure_never_submits_paid_task(self):
        image = self.root / "ref.png"
        Image.new("RGB", (8, 8), "blue").save(image)
        self.args.image = [image]
        self.args.upload_provider = "tmpfiles"
        with patch.object(m, "upload_tmpfiles", side_effect=m.UserError("Upload failed"), create=True), patch.object(m, "api_call") as api:
            with self.assertRaises(m.UserError):
                m.submit(self.args)
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
