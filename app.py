import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configure OpenAI client
API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in .env file")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

USERS_FILE = "users.json"
SYSTEM_PROMPT = {"role": "system", "content": "You are an AI therapist. Your persona is that of a warm, empathetic, and down-to-earth friend who is a great listener. Your goal is to create a safe and comfortable space for users to share their thoughts and feelings. Sound natural, talk like a real person, not a machine. Use everyday language. Acknowledge and validate the user's feelings with phrases like 'That sounds really tough,' or 'I can understand why you'd feel that way.' Ask open-ended questions to encourage the user to talk more. Show genuine interest in their story. Do not give medical or clinical advice; your role is to help them explore their own feelings, not to solve their problems for them."}

def load_user_data():
    """Loads user data from the JSON file."""
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_user_data(data):
    """Saves user data to the JSON file."""
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_response(conversation_history):
    """Gets a response from the AI model."""
    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-3-8b-instruct",
            messages=conversation_history,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"An error occurred: {e}")
        return "I'm sorry, I'm having trouble connecting right now. Please try again later."

@app.route("/", methods=["GET", "POST"])
def index():
    """Handles the main chat interface for both guests and logged-in users."""
    history = []
    is_guest = "username" not in session

    if is_guest:
        # Use session for guest history
        if "guest_history" not in session:
            session["guest_history"] = [SYSTEM_PROMPT]
        history = session["guest_history"]
    else:
        # Load history for logged-in user
        username = session["username"]
        users_data = load_user_data()
        history = users_data.get(username, {}).get("history", [SYSTEM_PROMPT])

    if request.method == "POST":
        user_message = request.form.get("message")
        if user_message:
            history.append({"role": "user", "content": user_message})
            ai_response = get_response(history)
            history.append({"role": "assistant", "content": ai_response})
            
            if is_guest:
                session["guest_history"] = history
            else:
                users_data = load_user_data()
                if "username" in session:
                    users_data[session["username"]]["history"] = history
                    save_user_data(users_data)
        
    return render_template("chat.html", history_json=json.dumps(history), history=history)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Handles user registration."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users_data = load_user_data()

        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("register"))
        if username in users_data:
            flash("Username already exists.", "error")
            return redirect(url_for("register"))

        # Create new user
        hashed_password = generate_password_hash(password)
        users_data[username] = {"password_hash": hashed_password, "history": [SYSTEM_PROMPT]}
        
        # Merge guest history if it exists
        if "guest_history" in session and len(session["guest_history"]) > 1:
            users_data[username]["history"].extend(session["guest_history"][1:]) # Exclude system prompt
            session.pop("guest_history", None)

        save_user_data(users_data)
        session["username"] = username
        flash("Registration successful! Your conversation has been saved.", "success")
        return redirect(url_for("index"))
        
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handles user login."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users_data = load_user_data()

        user = users_data.get(username)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))
        
        # Merge guest history if it exists
        if "guest_history" in session and len(session["guest_history"]) > 1:
            user["history"].extend(session["guest_history"][1:])
            session.pop("guest_history", None)
            save_user_data(users_data)
            flash("Welcome back! Your previous session has been merged.", "success")
        
        session["username"] = username
        return redirect(url_for("index"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    """Logs the user out."""
    session.pop("username", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))

@app.route("/vr")
def vr():
    """Renders the VR experience page."""
    return render_template("vr.html")

@app.route('/vr-chat', methods=['POST'])
def vr_chat():
    """Handles the voice-to-voice chat in the VR environment."""
    data = request.get_json()
    user_message = data.get('message')

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    history = []
    is_guest = "username" not in session

    if is_guest:
        if "guest_history" not in session:
            session["guest_history"] = [SYSTEM_PROMPT]
        history = session["guest_history"]
    else:
        username = session["username"]
        users_data = load_user_data()
        history = users_data.get(username, {}).get("history", [SYSTEM_PROMPT])
    
    # Append user message and get AI response
    history.append({'role': 'user', 'content': user_message})
    response_text = get_response(history)
    history.append({'role': 'assistant', 'content': response_text})
    
    # Save the updated history
    if is_guest:
        session["guest_history"] = history
    else:
        users_data = load_user_data()
        if "username" in session:
            users_data[session["username"]]["history"] = history
            save_user_data(users_data)
    
    session.modified = True

    return jsonify({"reply": response_text})

@app.route("/clear")
def clear():
    """Clears the chat history."""
    session.pop("guest_history", None)
    if "username" in session:
        users_data = load_user_data()
        users_data[session["username"]]["history"] = [SYSTEM_PROMPT]
        save_user_data(users_data)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True) 