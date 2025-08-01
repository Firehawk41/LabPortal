import json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("form.html")


@app.route("/submit", methods=["POST"])
def submit():
    data = request.json

    # Optionally, process/validate/transform data here
    # For example, ensure 'samples' is a list of dicts, not a string

    # Write to file
    with open("submitted_request.json", "w") as f:
        json.dump(data, f, indent=2)

    return jsonify({"message": "Submission received and saved!"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000,debug=True)