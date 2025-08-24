import threading
from flask import Flask, request, render_template_string, redirect
from config import client, files_collection, BOT_USERNAME

# Import handlers so they register
import handlers.callbacks
import handlers.messages
import handlers.members
import commands.admin
import commands.user

flask_app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Iam Batman</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      text-align: center;
      padding: 50px;
      background: #fafafa;
    }
    #countdownMessage {
      font-size: 30px;
    }
    #scrollMessage {
      display: none;
      margin-top: 20px;
      font-weight: bold;
    }
    #linkSection {
      display: none;
      margin-top: 40px;
    }
    h1 {
  text-align: center;
  margin-top: 30px;
  font-size: 28px;
  word-break: break-word;
  max-width: 90%;
  margin-left: auto;
  margin-right: auto;
}

    #getLinkButton {
      padding: 10px 20px;
      font-size: 16px;
      background-color: #007bff;
      color: white;
      border: none;
      border-radius: 5px;
      cursor: pointer;
    }
    .ad-section {
      margin: 20px auto;
      padding: 10px;
      border: 1px solid #ccc;
      background: #f9f9f9;
      max-width: 100%;
      overflow: hidden;
      box-sizing: border-box;
    }
    .scroll {
      font-size: 38px;
    }

    @media (max-width: 600px) {
      #getLinkButton {
        width: 100%;
        font-size: 18px;
      }
      body {
        padding: 20px;
      }
      #countdownMessage {
        font-size: 38px;
        color: red;
        font-family:'Gill Sans', 'Gill Sans MT', Calibri, 'Trebuchet MS', sans-serif;
      }
      .scroll {
        font-size: 18px;
      }
    }
  </style>
</head>
<body>
  <h1>{{ file_name }}</h1>
  <p id="countdownMessage">Please wait for <span id="countdown">5</span> seconds...</p>
  <div class="scroll" id="scrollMessage">⬇ Scroll down to continue ⬇</div>

  {% for i in range(10) %}
 
  {% endfor %}

  <div id="linkSection">
    <a href="https://t.me/{{ bot_username }}?start=file_{{ msg_id }}">
      <button id="getLinkButton">📥 Get File</button>
    </a>
  </div>

  <script>
    let countdown = 5;
    const countdownEl = document.getElementById("countdown");
    const msgEl = document.getElementById("countdownMessage");
    const scrollMsg = document.getElementById("scrollMessage");
    const linkSection = document.getElementById("linkSection");

    const interval = setInterval(() => {
      countdown--;
      countdownEl.textContent = countdown;
      if (countdown <= 0) {
        clearInterval(interval);
        msgEl.style.display = "none";
        scrollMsg.style.display = "block";
        linkSection.style.display = "block";
      }
    }, 1000);

    // Protection
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', function(e) {
      if (e.key === 'F12' || (e.ctrlKey || e.metaKey) && (
        ['U','S','P'].includes(e.key.toUpperCase()) ||
        (e.shiftKey && ['I','J','C','K'].includes(e.key.toUpperCase()))
      )) e.preventDefault();
    });
  </script>
</body>
</html>
'''

@flask_app.route('/redirect')
def redirect_page():
    msg_id = request.args.get("id")
    if not msg_id:
        return redirect(f"https://t.me/{BOT_USERNAME}")
    
    file_entry = files_collection.find_one({"message_id": int(msg_id)})
    file_name = file_entry.get("file_name", "Requested File") if file_entry else "Requested File"

    return render_template_string(
        HTML_TEMPLATE,
        msg_id=msg_id,
        bot_username=BOT_USERNAME,
        file_name=file_name
    )


def run_flask():
    flask_app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    client.run()
