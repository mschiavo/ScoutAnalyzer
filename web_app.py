import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from src.api.routes import router as api_router
from src.api.admin_routes import admin_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from src.db import get_database_url
        if not get_database_url():
            from src.storage_manager import StorageManager
            sm = StorageManager()
            if sm.backend == "s3" and sm.s3_client:
                sm.restore_database_from_storage()
    except Exception as e:
        print(f"Warning: restore_database_from_storage on startup: {e}")

    try:
        from src.db import get_database_url
        if get_database_url():
            from scripts.migrate_sqlite_to_postgres import setup_and_seed_postgres
            setup_and_seed_postgres()
        else:
            from database.setup_db import create_database
            from src.db import get_sqlite_path
            create_database(get_sqlite_path())
    except Exception as e:
        print(f"Warning: database setup on startup failed: {e}")
    yield

app = FastAPI(
    title="ScoutAnalyzer Web API & Dashboard",
    description="Piattaforma di Audit, Ispezione e Validazione Regolamentare per File Scout Data Volley (.dvw)",
    version="1.2.0",
    lifespan=lifespan
)

# Abilitazione CORS per consentire l'accesso sia alla SPA interna che a frontend esterni (es. app Vite su porta 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Inclusione delle rotte API
app.include_router(api_router)
app.include_router(admin_router)

# Mount della directory dei file statici frontend (se presente)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def serve_frontend_root():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return RedirectResponse(url="/docs")
else:
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def redirect_to_docs():
        return RedirectResponse(url="/docs")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    is_prod = bool(os.environ.get("PORT"))
    print(f"Avvio del server ScoutAnalyzer Web su http://{host}:{port} ...")
    uvicorn.run("web_app:app", host=host, port=port, reload=not is_prod)
