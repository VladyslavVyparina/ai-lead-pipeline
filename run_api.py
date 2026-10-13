import uvicorn

from app.config import settings

if __name__ == "__main__":
    # Rendered QA writes screenshots and local preview HTML under ``artifacts``.
    # Those outputs are runtime data, not source changes; watching them restarts
    # Uvicorn halfway through a browser QA run on local development machines.
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        reload_excludes=["artifacts/*", "pipeline*.db*"],
    )
