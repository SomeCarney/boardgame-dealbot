"""Builds Amazon Associates links. Deliberately does not call the Product
Advertising API -- a tagged link is just a URL parameter, and PA API access
requires sales volume this project won't have on day one (see plan)."""

from __future__ import annotations

import os


class MissingAssociateTag(RuntimeError):
    pass


def build_affiliate_link(asin: str, domain: str = "www.amazon.com") -> str:
    tag = os.environ.get("AMAZON_ASSOCIATE_TAG")
    if not tag:
        if os.environ.get("DRY_RUN") == "1":
            tag = "EXAMPLE-20"
        else:
            raise MissingAssociateTag(
                "AMAZON_ASSOCIATE_TAG is not set. Add it as a GitHub Actions secret "
                "once your Associates application is approved, or set DRY_RUN=1 to test "
                "without one."
            )
    return f"https://{domain}/dp/{asin}?tag={tag}"
