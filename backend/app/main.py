from fastapi import FastAPI

app = FastAPI(title="Dev-Hive API", version="0.1.0")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# 라우터는 app/api/ 아래에 추가하고 여기서 include
# from app.api import content, recommend, user
# app.include_router(content.router)
# app.include_router(recommend.router)
# app.include_router(user.router)
