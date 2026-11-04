import os
import logging
import requests

logger = logging.getLogger(__name__)


def publish_post(draft: dict) -> str | None:
    if os.getenv("BLOG_MOCK_MODE", "false").lower() == "true":
        slug = (draft.get("keyword") or draft.get("title", "post")).lower().replace(" ", "-")[:50]
        return f"https://mockblog.example.com/{slug}"

    endpoint = os.getenv("BLOG_API_ENDPOINT", "")
    token    = os.getenv("BLOG_API_TOKEN", "")
    adapter  = os.getenv("BLOG_API_ADAPTER", "custom")

    if not endpoint:
        logger.error("BLOG_API_ENDPOINT not set")
        return None

    if adapter == "wordpress":
        payload = {
            "title": draft["title"],
            "content": draft["draft_content"],
            "excerpt": draft.get("meta_description", ""),
            "status": "publish"
        }
    elif adapter == "ghost":
        payload = {
            "posts": [{
                "title": draft["title"],
                "html": draft["draft_content"],
                "custom_excerpt": draft.get("meta_description", ""),
                "status": "published"
            }]
        }
    else:
        payload = {
            "title": draft["title"],
            "content": draft["draft_content"],
            "meta_description": draft.get("meta_description", ""),
            "published": True
        }

    try:
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        url = data.get("url") or data.get("link") or data.get("permalink")
        if not url:
            logger.error(f"Blog publish: response had no url/link/permalink field. Response keys: {list(data.keys())}")
            return None
        return url
    except Exception as e:
        logger.error(f"Blog publish failed: {e}")
        return None
