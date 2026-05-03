from webapp import LOGGER, build_database_url, create_app


app = create_app()


if __name__ == "__main__":
    LOGGER.info("Starting app with database %s", build_database_url())
    app.run(host="0.0.0.0", port=5000, threaded=True)
