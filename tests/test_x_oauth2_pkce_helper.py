from scripts.x_oauth2_pkce import DEFAULT_SCOPES, build_authorize_url, make_code_challenge


def test_authorize_url_requests_media_write_and_offline_access():
    url = build_authorize_url(
        client_id="client-id",
        redirect_uri="http://127.0.0.1:8080/callback",
        state="state-123",
        code_challenge="challenge-123",
    )

    assert "https://x.com/i/oauth2/authorize?" in url
    assert "client_id=client-id" in url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8080%2Fcallback" in url
    assert "media.write" in DEFAULT_SCOPES
    assert "offline.access" in DEFAULT_SCOPES
    assert "scope=tweet.read+tweet.write+users.read+media.write+offline.access" in url


def test_code_challenge_is_base64url_sha256_without_padding():
    challenge = make_code_challenge("a" * 64)

    assert "=" not in challenge
    assert "+" not in challenge
    assert "/" not in challenge
    assert len(challenge) == 43
