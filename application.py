from app import app

# This file serves as an entry point for gunicorn in deployment
# Use: gunicorn application:app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)