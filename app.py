
import identity
import identity.web
import requests
from flask import Flask, redirect, render_template, request, session, url_for, jsonify
from flask_session import Session
import app_config
from utils import generate_response

app = Flask(__name__)
app.config.from_object(app_config)
Session(app)

# This section is needed for url_for("foo", _external=True) to automatically
# generate http scheme when this sample is running on localhost,
# and to generate https scheme when it is deployed behind reversed proxy.
# See also https://flask.palletsprojects.com/en/2.2.x/deploying/proxy_fix/
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

auth = identity.web.Auth(
    session=session,
    authority=app.config.get("AUTHORITY"),
    client_id=app.config["CLIENT_ID"],
    client_credential=app.config["CLIENT_SECRET"],
)


@app.route('/')
def home():
    return render_template('home.html')


@app.route("/sign-in")
def login():
    return render_template("login.html", version=identity.__version__, **auth.log_in(
        scopes=app_config.SCOPE, # Have user consent to scopes during log-in
        redirect_uri=url_for("auth_response", _external=True), # Optional. If present, this absolute URL must match your app's redirect_uri registered in Azure Portal
        ))


@app.route(app_config.REDIRECT_PATH)
def auth_response():
    result = auth.complete_log_in(request.args)
    if "error" in result:
        return render_template("auth_error.html", result=result)
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    return redirect(auth.log_out(url_for("index", _external=True)))


@app.route("/")
def index():
    if not (app.config["CLIENT_ID"] and app.config["CLIENT_SECRET"]):
        # This check is not strictly necessary.
        # You can remove this check from your production code.
        return render_template('config_error.html')
    if not auth.get_user():
        return redirect(url_for("login"))
    return render_template('index.html', user=auth.get_user(), version=identity.__version__)


@app.route("/call_downstream_api")
def call_downstream_api():
    token = auth.get_token_for_user(app_config.SCOPE)
    if "error" in token:
        return redirect(url_for("login"))
    # Use access token to call downstream api
    api_result = requests.get(
        app_config.ENDPOINT,
        headers={'Authorization': 'Bearer ' + token['access_token']},
        timeout=30,
    ).json()
    return render_template('display.html', result=api_result, token=token['access_token'])


@app.route("/chat/reply", methods=["POST"])
def chat_reply():
    token = request.json.get('token')
    to_email = request.json.get('to_email')
    body_text = request.json.get('replyBody')
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    res = generate_response(body_text)
    data = {
        "message": {
            "toRecipients": [{"emailAddress": {"address": to_email}}],
            "subject": f"Re: Auto reply",
            "body": {"contentType": "Text", "content": res},
        },
        "saveToSentItems": "true"
    }
    response = requests.post(f"{app_config.GRAPH_API_URL}/me/sendMail", headers=headers, json=data)
    if response.status_code == 202:
        return jsonify({'success': True, 'message': f"Reply sent successfully to {to_email}."})
    return jsonify({'success': False, 'message': response.text})


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
