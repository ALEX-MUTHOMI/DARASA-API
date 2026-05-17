from __future__ import annotations

import inspect

import pytest
from django.core.exceptions import ValidationError

from curriculum.algorithms.source_url_validator import validate_source_url


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


@pytest.mark.parametrize(
    "url",
    [
        "http://kicd.ac.ke/update.pdf",
        "https://kicd.ac.ke:8443/update.pdf",
        "https://kicd.ac.ke.evil.com/update.pdf",
        "https://evil.com/redirect?next=https://kicd.ac.ke",
        "https://user:pass@kicd.ac.ke/update.pdf",
        "https://127.0.0.1/admin",
        "https://localhost/admin",
        "https://0.0.0.0/admin",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.1/internal",
        "https://192.168.1.10/internal",
        "https://172.16.0.1/internal",
        "https://[::1]/internal",
        "https://xn--fake-kicd-domain.example/update.pdf",
    ],
)
def test_malicious_official_source_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        validate_source_url(url, allowed_domains=["kicd.ac.ke", "www.kicd.ac.ke"])


def test_source_url_validator_normalizes_approved_metadata_without_fetching():
    assert (
        validate_source_url(
            "HTTPS://KICD.AC.KE/cbc-materials/curriculum-designs/?v=2026",
            allowed_domains=["kicd.ac.ke"],
        )
        == "https://kicd.ac.ke/cbc-materials/curriculum-designs/?v=2026"
    )


def test_cct_code_does_not_fetch_submitted_urls_in_hot_paths():
    import curriculum.algorithms.source_url_validator as source_url_validator
    import curriculum.algorithms.ssrf_guard as ssrf_guard

    source = "\n".join(
        inspect.getsource(module)
        for module in [
            source_url_validator,
            ssrf_guard,
        ]
    )
    forbidden = [
        "requests.",
        "httpx.",
        "urllib.request",
        "aiohttp",
        "socket.",
        "selenium",
        "playwright",
        "BeautifulSoup",
        "scrapy",
    ]

    assert not any(token in source for token in forbidden)
