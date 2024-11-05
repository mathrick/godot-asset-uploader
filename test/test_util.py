import random
import string

import pytest

from godot_asset_uploader.util import (
    VIDEO_EXTS,
    is_interesting_link, is_image_link, normalise_video_link,
    prettyprint_list,
)

YOUTUBE_CANONICAL_URL = "https://youtube.com/watch?v={id}"

YOUTUBE_SUPPORTED_URLS = (
    "http://www.youtube.com/watch?v={id}",
    "http://youtube.com/watch?v={id}",
    "http://m.youtube.com/watch?v={id}",
    "https://www.youtube.com/watch?v={id}",
    "https://youtube.com/watch?v={id}",
    "https://m.youtube.com/watch?v={id}",

    "http://www.youtube.com/watch?v={id}&feature=em-uploademail",
    "http://youtube.com/watch?v={id}&feature=em-uploademail",
    "http://m.youtube.com/watch?v={id}&feature=em-uploademail",
    "https://www.youtube.com/watch?v={id}&feature=em-uploademail",
    "https://youtube.com/watch?v={id}&feature=em-uploademail",
    "https://m.youtube.com/watch?v={id}&feature=em-uploademail",

    "http://www.youtube.com/watch?v={id}&feature=feedrec_grec_index",
    "http://youtube.com/watch?v={id}&feature=feedrec_grec_index",
    "http://m.youtube.com/watch?v={id}&feature=feedrec_grec_index",
    "https://www.youtube.com/watch?v={id}&feature=feedrec_grec_index",
    "https://youtube.com/watch?v={id}&feature=feedrec_grec_index",
    "https://m.youtube.com/watch?v={id}&feature=feedrec_grec_index",

    "http://www.youtube.com/watch?v={id}#t=0m10s",
    "http://youtube.com/watch?v={id}#t=0m10s",
    "http://m.youtube.com/watch?v={id}#t=0m10s",
    "https://www.youtube.com/watch?v={id}#t=0m10s",
    "https://youtube.com/watch?v={id}#t=0m10s",
    "https://m.youtube.com/watch?v={id}#t=0m10s",

    "http://www.youtube.com/watch?v={id}&feature=channel",
    "http://youtube.com/watch?v={id}&feature=channel",
    "http://m.youtube.com/watch?v={id}&feature=channel",
    "https://www.youtube.com/watch?v={id}&feature=channel",
    "https://youtube.com/watch?v={id}&feature=channel",
    "https://m.youtube.com/watch?v={id}&feature=channel",

    "http://www.youtube.com/watch?v={id}&playnext_from=TL&videos=osPknwzXEas&feature=sub",
    "http://youtube.com/watch?v={id}&playnext_from=TL&videos=osPknwzXEas&feature=sub",
    "http://m.youtube.com/watch?v={id}&playnext_from=TL&videos=osPknwzXEas&feature=sub",
    "https://www.youtube.com/watch?v={id}&playnext_from=TL&videos=osPknwzXEas&feature=sub",
    "https://youtube.com/watch?v={id}&playnext_from=TL&videos=osPknwzXEas&feature=sub",
    "https://m.youtube.com/watch?v={id}&playnext_from=TL&videos=osPknwzXEas&feature=sub",

    "http://www.youtube.com/watch?v={id}&feature=youtu.be",
    "http://youtube.com/watch?v={id}&feature=youtu.be",
    "http://m.youtube.com/watch?v={id}&feature=youtu.be",
    "https://www.youtube.com/watch?v={id}&feature=youtu.be",
    "https://youtube.com/watch?v={id}&feature=youtu.be",
    "https://m.youtube.com/watch?v={id}&feature=youtu.be",

    "http://www.youtube.com/watch?v={id}&feature=youtube_gdata_player",
    "http://youtube.com/watch?v={id}&feature=youtube_gdata_player",
    "http://m.youtube.com/watch?v={id}&feature=youtube_gdata_player",
    "https://www.youtube.com/watch?v={id}&feature=youtube_gdata_player",
    "https://youtube.com/watch?v={id}&feature=youtube_gdata_player",
    "https://m.youtube.com/watch?v={id}&feature=youtube_gdata_player",

    "http://www.youtube.com/watch?v={id}&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655",
    "http://youtube.com/watch?v={id}&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655",
    "http://m.youtube.com/watch?v={id}&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655",
    "https://www.youtube.com/watch?v={id}&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655",
    "https://youtube.com/watch?v={id}&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655",
    "https://m.youtube.com/watch?v={id}&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655",

    "http://www.youtube.com/watch?feature=player_embedded&v={id}",
    "http://youtube.com/watch?feature=player_embedded&v={id}",
    "http://m.youtube.com/watch?feature=player_embedded&v={id}",
    "https://www.youtube.com/watch?feature=player_embedded&v={id}",
    "https://youtube.com/watch?feature=player_embedded&v={id}",
    "https://m.youtube.com/watch?feature=player_embedded&v={id}",

    "http://www.youtube.com/watch?app=desktop&v={id}",
    "http://youtube.com/watch?app=desktop&v={id}",
    "http://m.youtube.com/watch?app=desktop&v={id}",
    "https://www.youtube.com/watch?app=desktop&v={id}",
    "https://youtube.com/watch?app=desktop&v={id}",
    "https://m.youtube.com/watch?app=desktop&v={id}",

    "http://www.youtube.com/watch/{id}",
    "http://youtube.com/watch/{id}",
    "http://m.youtube.com/watch/{id}",
    "https://www.youtube.com/watch/{id}",
    "https://youtube.com/watch/{id}",
    "https://m.youtube.com/watch/{id}",

    "http://www.youtube.com/watch/{id}?app=desktop",
    "http://youtube.com/watch/{id}?app=desktop",
    "http://m.youtube.com/watch/{id}?app=desktop",
    "https://www.youtube.com/watch/{id}?app=desktop",
    "https://youtube.com/watch/{id}?app=desktop",
    "https://m.youtube.com/watch/{id}?app=desktop",

    "http://www.youtube.com/v/{id}",
    "http://youtube.com/v/{id}",
    "http://m.youtube.com/v/{id}",
    "https://www.youtube.com/v/{id}",
    "https://youtube.com/v/{id}",
    "https://m.youtube.com/v/{id}",

    "http://www.youtube.com/v/{id}?version=3&autohide=1",
    "http://youtube.com/v/{id}?version=3&autohide=1",
    "http://m.youtube.com/v/{id}?version=3&autohide=1",
    "https://www.youtube.com/v/{id}?version=3&autohide=1",
    "https://youtube.com/v/{id}?version=3&autohide=1",
    "https://m.youtube.com/v/{id}?version=3&autohide=1",

    "http://www.youtube.com/v/{id}?fs=1&hl=en_US&rel=0",
    "http://youtube.com/v/{id}?fs=1&hl=en_US&rel=0",
    "http://m.youtube.com/v/{id}?fs=1&hl=en_US&rel=0",
    "https://www.youtube.com/v/{id}?fs=1&amp;hl=en_US&amp;rel=0",
    "https://www.youtube.com/v/{id}?fs=1&hl=en_US&rel=0",
    "https://youtube.com/v/{id}?fs=1&hl=en_US&rel=0",
    "https://m.youtube.com/v/{id}?fs=1&hl=en_US&rel=0",

    "http://www.youtube.com/v/{id}?feature=youtube_gdata_player",
    "http://youtube.com/v/{id}?feature=youtube_gdata_player",
    "http://m.youtube.com/v/{id}?feature=youtube_gdata_player",
    "https://www.youtube.com/v/{id}?feature=youtube_gdata_player",
    "https://youtube.com/v/{id}?feature=youtube_gdata_player",
    "https://m.youtube.com/v/{id}?feature=youtube_gdata_player",

    "http://youtu.be/{id}",
    "https://youtu.be/{id}",

    "http://youtu.be/{id}?feature=youtube_gdata_player",
    "https://youtu.be/{id}?feature=youtube_gdata_player",

    "http://youtu.be/{id}?list=PLToa5JuFMsXTNkrLJbRlB--76IAOjRM9b",
    "https://youtu.be/{id}?list=PLToa5JuFMsXTNkrLJbRlB--76IAOjRM9b",

    "http://youtu.be/{id}&feature=channel",
    "https://youtu.be/{id}&feature=channel",

    "http://youtu.be/{id}?t=1",
    "http://youtu.be/{id}?t=1s",
    "https://youtu.be/{id}?t=1",
    "https://youtu.be/{id}?t=1s",

    "http://youtu.be/{id}?si=B_RZg_I-lLaa7UU-",
    "https://youtu.be/{id}?si=B_RZg_I-lLaa7UU-",

    "http://www.youtube.com/oembed?url=http%3A//www.youtube.com/watch?v%3D{id}&format=json",
    "http://youtube.com/oembed?url=http%3A//www.youtube.com/watch?v%3D{id}&format=json",
    "http://m.youtube.com/oembed?url=http%3A//www.youtube.com/watch?v%3D{id}&format=json",
    "https://www.youtube.com/oembed?url=http%3A//www.youtube.com/watch?v%3D{id}&format=json",
    "https://youtube.com/oembed?url=http%3A//www.youtube.com/watch?v%3D{id}&format=json",
    "https://m.youtube.com/oembed?url=http%3A//www.youtube.com/watch?v%3D{id}&format=json",

    "http://www.youtube.com/embed/{id}",
    "http://youtube.com/embed/{id}",
    "http://m.youtube.com/embed/{id}",
    "https://www.youtube.com/embed/{id}",
    "https://youtube.com/embed/{id}",
    "https://m.youtube.com/embed/{id}",

    "http://www.youtube.com/embed/{id}?rel=0",
    "http://youtube.com/embed/{id}?rel=0",
    "http://m.youtube.com/embed/{id}?rel=0",
    "https://www.youtube.com/embed/{id}?rel=0",
    "https://youtube.com/embed/{id}?rel=0",
    "https://m.youtube.com/embed/{id}?rel=0",

    "http://www.youtube-nocookie.com/embed/{id}?rel=0",
    "https://www.youtube-nocookie.com/embed/{id}?rel=0",

    "http://www.youtube.com/e/{id}",
    "http://youtube.com/e/{id}",
    "http://m.youtube.com/e/{id}",
    "https://www.youtube.com/e/{id}",
    "https://youtube.com/e/{id}",
    "https://m.youtube.com/e/{id}",

    "http://www.youtube.com/shorts/{id}",
    "http://youtube.com/shorts/{id}",
    "http://m.youtube.com/shorts/{id}",
    "https://www.youtube.com/shorts/{id}",
    "https://youtube.com/shorts/{id}",
    "https://m.youtube.com/shorts/{id}",

    "http://www.youtube.com/shorts/{id}?app=desktop",
    "http://youtube.com/shorts/{id}?app=desktop",
    "http://m.youtube.com/shorts/{id}?app=desktop",
    "https://www.youtube.com/shorts/{id}?app=desktop",
    "https://youtube.com/shorts/{id}?app=desktop",
    "https://m.youtube.com/shorts/{id}?app=desktop",

    "http://www.youtube.com/live/{id}",
    "http://youtube.com/live/{id}",
    "http://m.youtube.com/live/{id}",
    "https://www.youtube.com/live/{id}",
    "https://youtube.com/live/{id}",
    "https://m.youtube.com/live/{id}",

    "http://www.youtube.com/live/{id}?app=desktop",
    "http://youtube.com/live/{id}?app=desktop",
    "http://m.youtube.com/live/{id}?app=desktop",
    "https://www.youtube.com/live/{id}?app=desktop",
    "https://youtube.com/live/{id}?app=desktop",
    "https://m.youtube.com/live/{id}?app=desktop",
)

YOUTUBE_UNSUPPORTED_URLS = (
    "http://www.youtube.com/attribution_link?a=JdfC0C9V6ZI&u=%2Fwatch%3Fv%3DEhxJLojIE_o%26feature%3Dshare",
    "http://youtube.com/attribution_link?a=JdfC0C9V6ZI&u=%2Fwatch%3Fv%3DEhxJLojIE_o%26feature%3Dshare",
    "http://m.youtube.com/attribution_link?a=JdfC0C9V6ZI&u=%2Fwatch%3Fv%3DEhxJLojIE_o%26feature%3Dshare",
    "https://www.youtube.com/attribution_link?a=JdfC0C9V6ZI&u=%2Fwatch%3Fv%3DEhxJLojIE_o%26feature%3Dshare",
    "https://youtube.com/attribution_link?a=JdfC0C9V6ZI&u=%2Fwatch%3Fv%3DEhxJLojIE_o%26feature%3Dshare",
    "https://m.youtube.com/attribution_link?a=JdfC0C9V6ZI&u=%2Fwatch%3Fv%3DEhxJLojIE_o%26feature%3Dshare",

    "http://www.youtube.com/attribution_link?a=8g8kPrPIi-ecwIsS&u=/watch%3Fv%3D{id}%26feature%3Dem-uploademail",
    "http://youtube.com/attribution_link?a=8g8kPrPIi-ecwIsS&u=/watch%3Fv%3D{id}%26feature%3Dem-uploademail",
    "http://m.youtube.com/attribution_link?a=8g8kPrPIi-ecwIsS&u=/watch%3Fv%3D{id}%26feature%3Dem-uploademail",
    "https://www.youtube.com/attribution_link?a=8g8kPrPIi-ecwIsS&u=/watch%3Fv%3D{id}%26feature%3Dem-uploademail",
    "https://youtube.com/attribution_link?a=8g8kPrPIi-ecwIsS&u=/watch%3Fv%3D{id}%26feature%3Dem-uploademail",
    "https://m.youtube.com/attribution_link?a=8g8kPrPIi-ecwIsS&u=/watch%3Fv%3D{id}%26feature%3Dem-uploademail",
)


def alnum_string(length):
    return ''.join(random.choice(
        string.ascii_uppercase + string.ascii_lowercase + string.digits
    ) for _ in range(length))


def random_paths(*exts):
    path = "/".join([alnum_string(random.randint(4, 10))
                     for _ in range(random.randint(1, 3))])
    for ext in exts:
        yield f"{path}{ext}"


IMAGE_FILE_PATHS = list(random_paths(".jpg", ".png", ".webp", ".gif"))
VIDEO_FILE_PATHS = list(random_paths(".mp4", ".mov", ".mkv", ".webm", ".avi", ".ogv", ".ogg"))
OTHER_FILE_PATHS = list(random_paths(".txt", ".html", ".json", ""))


def random_url_parts():
    for scheme in SCHEMES:
        for domain in DOMAINS:
            for query in QUERIES:
                yield (scheme, domain, query)


SCHEMES = ["ftp", "http", "https"]
DOMAINS = [
    f"{alnum_string(4)}.{alnum_string(10)}.{tld}" for _ in range(5)
    for tld in [".com", ".org", ".co.uk", ".pl", ".xyz"]
]
QUERIES = ["", "?foo=bar", "?foo=bar&baz=quux"]


# NB: is_interesting_link() doesn't care what the link is to, just
# that it's a regular http(s) link
@pytest.mark.parametrize("path", IMAGE_FILE_PATHS + VIDEO_FILE_PATHS + OTHER_FILE_PATHS)
def test_is_interesting_link(path):
    for scheme, domain, query in random_url_parts():
        url = f"{scheme}://{domain}/{path}{query}"
        if scheme != "ftp":
            assert is_interesting_link(url)
        else:
            assert not is_interesting_link(url)
    for domain in DOMAINS:
        email = f"{alnum_string(10)}@domain"
        assert not is_interesting_link(email)
        assert not is_interesting_link(f"mailto:{email}")


@pytest.mark.parametrize("path", IMAGE_FILE_PATHS)
def test_is_image_link(path):
    for scheme, domain, query in random_url_parts():
        assert is_image_link(f"{scheme}://{domain}/{path}{query}")


@pytest.mark.parametrize("path", OTHER_FILE_PATHS)
def test_is_not_image_link(path):
    for scheme, domain, query in random_url_parts():
        assert not is_image_link(f"{scheme}://{domain}/{path}{query}")


def test_normalise_youtube_link():
    video_id = alnum_string(12)
    canonical = YOUTUBE_CANONICAL_URL.format(id=video_id)

    for link in YOUTUBE_SUPPORTED_URLS:
        assert normalise_video_link(link.format(id=video_id)) == canonical


def test_normalise_youtube_link_unsupported():
    video_id = alnum_string(12)
    for link in YOUTUBE_UNSUPPORTED_URLS:
        assert normalise_video_link(link.format(id=video_id)) is None


@pytest.mark.parametrize("path", VIDEO_FILE_PATHS)
def test_normalise_video_link(path):
    for scheme, domain, query in random_url_parts():
        url = f"{scheme}://{domain}/{path}{query}"
        assert normalise_video_link(url) == url


@pytest.mark.parametrize("path", OTHER_FILE_PATHS)
def test_normalise_video_link_not_video(path):
    for scheme, domain, query in random_url_parts():
        url = f"{scheme}://{domain}/{path}{query}"
        assert normalise_video_link(url) == None


PRETTYPRINT_INPUTS = [
    (["foo"                       ], "{}"                 ),
    (["foo", "bar"                ], "{} and {}"          ),
    (["foo", "bar", "baz"         ], "{}, {}, and {}"     ),
    (["foo", "bar", "baz", "quux" ], "{}, {}, {}, and {}" ),
]


@pytest.mark.parametrize("input, expected_output", [([], "")] + PRETTYPRINT_INPUTS)
def test_prettyprint_list(input, expected_output):
    assert prettyprint_list(input) == expected_output.format(*input)
