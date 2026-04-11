import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response

PROMISES_SERVICE_URL = os.getenv("PROMISES_SERVICE_URL", "http://promises-service:8001")
POLITICIANS_SERVICE_URL = os.getenv("POLITICIANS_SERVICE_URL", "http://politicians-service:8002")
TRACKERS_SERVICE_URL = os.getenv("TRACKERS_SERVICE_URL", "http://trackers-service:8003")
SOURCES_SERVICE_URL = os.getenv("SOURCES_SERVICE_URL", "http://sources-service:8004")
PROJECTION_SERVICE_URL = os.getenv("PROJECTION_SERVICE_URL", "http://projection-service:8005")


@asynccontextmanager
async def lifespan(app: FastAPI):
	app.state.client = httpx.AsyncClient(timeout=None)
	try:
		yield
	finally:
		await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


async def proxy_request(request: Request, method: str, base_url: str, path: str) -> Response:
	client: httpx.AsyncClient = request.app.state.client
	body = await request.body()

	downstream_response = await client.request(
		method=method,
		url=f"{base_url}{path}",
		headers=dict(request.headers),
		params=request.query_params,
		content=body,
	)

	return Response(
		content=downstream_response.content,
		status_code=downstream_response.status_code,
		headers=dict(downstream_response.headers),
	)


@app.get("/health")
async def health() -> dict[str, str]:
	return {"status": "ok"}


@app.post("/promises")
async def create_promise(request: Request) -> Response:
	return await proxy_request(request, "POST", PROMISES_SERVICE_URL, "/promises")


@app.get("/promises/{promise_id}")
async def get_promise(promise_id: str, request: Request) -> Response:
	return await proxy_request(request, "GET", PROMISES_SERVICE_URL, f"/promises/{promise_id}")


@app.patch("/promises/{promise_id}")
async def update_promise(promise_id: str, request: Request) -> Response:
	return await proxy_request(request, "PATCH", PROMISES_SERVICE_URL, f"/promises/{promise_id}")


@app.patch("/promises/{promise_id}/status")
async def retract_promise(promise_id: str, request: Request) -> Response:
	return await proxy_request(
		request,
		"PATCH",
		PROMISES_SERVICE_URL,
		f"/promises/{promise_id}/status",
	)


@app.post("/politicians")
async def create_politician(request: Request) -> Response:
	return await proxy_request(request, "POST", POLITICIANS_SERVICE_URL, "/politicians")


@app.get("/politicians/{politician_id}")
async def get_politician(politician_id: str, request: Request) -> Response:
	return await proxy_request(
		request,
		"GET",
		POLITICIANS_SERVICE_URL,
		f"/politicians/{politician_id}",
	)


@app.get("/tracking/{promise_id}")
async def get_tracking(promise_id: str, request: Request) -> Response:
	return await proxy_request(request, "GET", TRACKERS_SERVICE_URL, f"/tracking/{promise_id}")


@app.patch("/tracking/{promise_id}")
async def update_tracking(promise_id: str, request: Request) -> Response:
	return await proxy_request(request, "PATCH", TRACKERS_SERVICE_URL, f"/tracking/{promise_id}")


@app.post("/sources")
async def create_source(request: Request) -> Response:
	return await proxy_request(request, "POST", SOURCES_SERVICE_URL, "/sources")


@app.post("/sources/link")
async def link_source(request: Request) -> Response:
	return await proxy_request(request, "POST", SOURCES_SERVICE_URL, "/sources/link")


@app.get("/sources/promise/{promise_id}")
async def get_sources_by_promise(promise_id: str, request: Request) -> Response:
	return await proxy_request(
		request,
		"GET",
		SOURCES_SERVICE_URL,
		f"/sources/promise/{promise_id}",
	)


@app.get("/query/promises")
async def query_promises(request: Request) -> Response:
	return await proxy_request(request, "GET", PROJECTION_SERVICE_URL, "/query/promises")


@app.get("/query/promises/{promise_id}")
async def query_promise_by_id(promise_id: str, request: Request) -> Response:
	return await proxy_request(
		request,
		"GET",
		PROJECTION_SERVICE_URL,
		f"/query/promises/{promise_id}",
	)
