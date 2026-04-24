"""Entry point: python -m smart_telescope  or  smarttscope CLI."""
import uvicorn


def main() -> None:
    uvicorn.run("smart_telescope.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
