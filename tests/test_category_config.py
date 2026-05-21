import inspect
import unittest

import ai_news_discord
from lib import claude_client, discord_client, sources


class CategoryConfigTest(unittest.TestCase):
    def test_creative_ai_category_is_configured_end_to_end(self):
        self.assertIn("creative_ai", sources.X_QUERIES)
        self.assertIn("Midjourney", sources.X_QUERIES["creative_ai"])
        self.assertIn("Runway", sources.X_QUERIES["creative_ai"])
        self.assertIn("Sora", sources.X_QUERIES["creative_ai"])
        self.assertIn("creative_ai", claude_client._CRITERIA)
        self.assertIn("AI画像", claude_client._CRITERIA["creative_ai"])
        self.assertIn("AI動画", claude_client._CRITERIA["creative_ai"])
        self.assertIn("creative_ai", discord_client._EMBED_META)

        main_source = inspect.getsource(ai_news_discord.main)
        self.assertIn('fetch_x_posts("creative_ai"', main_source)
        self.assertIn('filter_and_translate(creative_items, "creative_ai"', main_source)

    def test_company_updates_category_is_configured_end_to_end(self):
        self.assertIn("company_updates", sources.X_QUERIES)
        self.assertIn("from:OpenAI", sources.X_QUERIES["company_updates"])
        self.assertIn("from:AnthropicAI", sources.X_QUERIES["company_updates"])
        self.assertIn("from:Microsoft", sources.X_QUERIES["company_updates"])
        self.assertIn("company_updates", claude_client._CRITERIA)
        self.assertIn("各社", claude_client._CRITERIA["company_updates"])
        self.assertIn("API", claude_client._CRITERIA["company_updates"])
        self.assertIn("company_updates", discord_client._EMBED_META)

        main_source = inspect.getsource(ai_news_discord.main)
        self.assertIn('fetch_x_posts("company_updates"', main_source)
        self.assertIn(
            'filter_and_translate(company_items, "company_updates"',
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
