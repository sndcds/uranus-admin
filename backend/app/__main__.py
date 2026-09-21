import uvicorn

from app.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
        access_log=False,
        workers=1,  # Own the global SQL console concurrency limit.
        # Explicit supported driver: bounded frames and complete HTTP upgrade denials.
        ws="wsproto",
        ws_max_size=200_000,
    )


if __name__ == "__main__":
    main()
