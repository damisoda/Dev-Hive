from fastapi import FastAPI

from app.api import auth, content, graph, progress, recommend

app = FastAPI(title="Dev-Hive API", version="0.1.0")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


# 라우터 등록
app.include_router(auth.router)
app.include_router(content.router)
app.include_router(recommend.router)
app.include_router(progress.router)
app.include_router(graph.router)
