from fastapi import Request

TRACE_HEADERS = [
    "x-request-id",
    "x-b3-traceid",
    "x-b3-spanid",
    "x-b3-parentspanid",
    "x-b3-sampled",
    "x-b3-flags",
    "b3",
]


def forward_headers(request: Request) -> dict:
    """Extract tracing headers from the incoming request and return a dict suitable
    for forwarding to downstream services.
    """
    headers: dict = {}
    for name in TRACE_HEADERS:
        val = request.headers.get(name)
        if val is not None:
            headers[name] = val
    return headers
