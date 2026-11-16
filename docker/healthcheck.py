import os
from urllib.request import Request, urlopen

host = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")[0].strip()
request = Request(
    f"http://127.0.0.1:{int(os.environ.get('PORT', '10000'))}/health/ready/",
    headers={"Host": host},
)
with urlopen(request, timeout=3) as response:
    if response.status != 200:
        raise SystemExit(1)
