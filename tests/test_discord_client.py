import json
import urllib.error
import unittest
from unittest.mock import patch

from lib.claude_client import CuratedItem
from lib.discord_client import build_embed
from lib.discord_client import send_embeds


class DiscordClientTest(unittest.TestCase):
    def test_build_embed_truncates_fields_to_discord_limits(self):
        embed = build_embed(
            "news",
            [
                CuratedItem(
                    title_ja="t" * 300,
                    summary_ja="s" * 2000,
                    url="https://example.com/" + "u" * 100,
                    source="source",
                )
            ],
        )

        self.assertIsNotNone(embed)
        self.assertLessEqual(len(embed["title"]), 256)
        self.assertLessEqual(len(embed["fields"][0]["name"]), 256)
        self.assertLessEqual(len(embed["fields"][0]["value"]), 1024)

    def test_send_embeds_splits_payloads_under_discord_embed_size_limit(self):
        sent_payloads = []

        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(req, timeout):
            sent_payloads.append(json.loads(req.data.decode("utf-8")))
            return Response()

        embeds = [
            {
                "title": f"category {i}",
                "description": "x" * 950,
                "fields": [
                    {
                        "name": "item",
                        "value": "y" * 200,
                        "inline": False,
                    }
                ],
            }
            for i in range(7)
        ]

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_embeds("https://discord.com/api/webhooks/test/token", embeds)

        self.assertGreater(len(sent_payloads), 1)
        for payload in sent_payloads:
            total_chars = sum(
                len(embed.get("title", ""))
                + len(embed.get("description", ""))
                + sum(
                    len(field.get("name", "")) + len(field.get("value", ""))
                    for field in embed.get("fields", [])
                )
                for embed in payload["embeds"]
            )
            self.assertLessEqual(total_chars, 6000)

    def test_send_embeds_retries_transient_discord_server_errors(self):
        attempts = 0

        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(req, timeout):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise urllib.error.HTTPError(
                    req.full_url,
                    500,
                    "Internal Server Error",
                    hdrs={},
                    fp=None,
                )
            return Response()

        with (
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            patch("time.sleep"),
        ):
            send_embeds(
                "https://discord.com/api/webhooks/test/token",
                [{"title": "test", "fields": []}],
            )

        self.assertEqual(attempts, 2)


if __name__ == "__main__":
    unittest.main()
