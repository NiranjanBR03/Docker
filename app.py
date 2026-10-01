
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Docker CI/CD Demo - Version 3"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)