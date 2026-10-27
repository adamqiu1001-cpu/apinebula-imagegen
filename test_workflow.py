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


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nebula 中文 空格 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prompt = self.root / "提示词.txt"
        self.prompt.write_text("雨夜城市", encoding="utf-8")
        self.args = argparse.Namespace(prompt_file=self.prompt, out_dir=self.root / "输出", image=[],
                                       image_url=[], model="gpt-image-2.5", quality="high", direct=False)
        self.key = patch.object(m, "get_key", return_value="test-key-never-log")
        self.key.start()
        self.addCleanup(self.key.stop)

    def create(self, result=None):
        with patch.object(m, "api_call", return_value=result or {"id": "task_test", "status": "queued"}) as call:
            m.submit(self.args)
            return call

    def state_args(self):
        return argparse.Namespace(state=self.args.out_dir / "state.json", direct=False)

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


if __name__ == "__main__":
    unittest.main()
