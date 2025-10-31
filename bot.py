import threading
from math import ceil
from flask import Flask, request, render_template_string, redirect, url_for
from pymongo import DESCENDING
from config import client, files_collection, BOT_USERNAME

# Import handlers so they register (if needed by your bot)
import handlers.callbacks
import handlers.messages
import handlers.members
import commands.admin
import commands.user

app = Flask(__name__)

# ---------- Common CSS / header fragments ----------
# Keep theme consistent across pages
COMMON_HEAD = """
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
:root{
  --bg:#0d1117; --card:#0f1620; --text:#e6f7fb;
  --primary:#00bcd4; --accent:#1e90ff;
  --muted:rgba(230,247,251,0.12);
}
*{box-sizing:border-box}
html,body{height:100%; margin:0; background:var(--bg); color:var(--text); font-family:Poppins,Inter,Segoe UI,Arial; -webkit-font-smoothing:antialiased}
a{color:inherit; text-decoration:none}
.container{width:100%; max-width:1100px; margin:0 auto; padding:24px}
.center-full { min-height:calc(100vh - 48px); display:flex; align-items:center; justify-content:center; flex-direction:column; text-align:center; padding:32px }
.glow-btn{background:linear-gradient(90deg,var(--accent),var(--primary)); color:#032; border:none; padding:12px 22px; border-radius:999px; cursor:pointer; box-shadow:0 6px 28px rgba(0,180,255,0.12); transition:transform .18s ease}
.glow-btn:hover{transform:translateY(-3px); box-shadow:0 12px 45px rgba(0,180,255,0.18)}
.card{background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); border:1px solid var(--muted); padding:18px; border-radius:12px}
.small{font-size:0.92rem; color:rgba(230,247,251,0.78)}
.grid{display:grid; gap:16px}
@media(min-width:900px){ .grid-cols-2{grid-template-columns:repeat(2,1fr)} }
@media(max-width:899px){ .grid-cols-2{grid-template-columns:1fr} }

/* subtle background gradients */
.page-bg {
  position:fixed; inset:0; z-index:-1;
  background:
    radial-gradient(circle at 10% 20%, rgba(0,188,212,0.06), transparent 12%),
    radial-gradient(circle at 90% 80%, rgba(33,150,243,0.06), transparent 12%);
  filter:blur(6px);
  transform:scale(1.05);
}
</style>
"""

# ---------- HOME TEMPLATE ----------
HOME_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <title>Home — File Portal</title>
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="icon" type="image/png" href="/static/favicon.png">
  """ + COMMON_HEAD + """
  <style>
    /* PUBG-like cinematic fade for the logo */
    .logo { width:200px; height:auto; opacity:0; transform:scale(1.18);
           filter: drop-shadow(0 0 14px rgba(0,188,212,0.55)) drop-shadow(0 0 30px rgba(30,144,255,0.45));
           animation: pubgFade 3.6s cubic-bezier(.2,.9,.2,1) forwards; }
    @keyframes pubgFade {
      0%   { opacity:0; transform:scale(1.4); filter:blur(10px); }
      55%  { opacity:1; transform:scale(1.03); filter:blur(2px); }
      100% { opacity:1; transform:scale(1); filter:blur(0); }
    }
    .title { font-size:1.6rem; margin-top:20px; color:var(--primary); opacity:0; transform:translateY(8px);
            animation: fadeUp .9s 3.8s forwards; }
    .subtitle { margin-top:10px; color:rgba(230,247,251,0.82); max-width:720px; opacity:0; transform:translateY(8px);
               animation: fadeUp .9s 4.0s forwards; }
    .home-actions{display:flex; gap:12px; margin-top:26px; opacity:0; transform:translateY(8px); animation:fadeUp .9s 4.2s forwards}
    @keyframes fadeUp{ to {opacity:1; transform:none} }
    .link-outline { padding:10px 18px; border-radius:10px; border:1px solid rgba(255,255,255,0.06); background:transparent; color:var(--text) }
  </style>
</head>
<body>
  <div class="page-bg"></div>
  <div class="center-full container" role="main" aria-labelledby="home-title">
    <img src="/static/logo.png" alt="Logo" class="logo" />
    <div id="home-title" class="title">Welcome to Batman's Files Storage</div>
    <div class="subtitle small">Get stored files via Telegram quickly. Use the portal to browse & get files.</div>

    <div class="home-actions">
      <button class="glow-btn" onclick="location.href='{{ url_for('files_list') }}'">📁 View Stored Files</button>
      
  </div>
</body>
</html>
"""

# ---------- REDIRECT TEMPLATE (faster loading bar + top menu + tight ads + popup on click) ----------
REDIRECT_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <title>Redirect — {{ file_name }}</title>
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="icon" type="image/png" href="/static/favicon.ico">
  """ + COMMON_HEAD + """
  <style>
    /* Navigation Bar */
    .top-nav {
      display:flex; justify-content:space-between; align-items:center;
      padding:10px 18px; position:fixed; top:0; left:0; width:100%;
      background:rgba(0,0,0,0.35); backdrop-filter:blur(10px);
      border-bottom:1px solid rgba(255,255,255,0.05);
      z-index:1000;
    }
    .top-nav a {
      color:var(--text); text-decoration:none; margin:0 8px;
      font-weight:500; font-size:0.95rem; transition:0.25s;
    }
    .top-nav a:hover { color:var(--primary); text-shadow:0 0 10px var(--primary); }

    .logo {
      width:150px; height:auto; margin:20px auto 10px auto;
      filter:drop-shadow(0 0 12px rgba(0,188,212,0.6)) drop-shadow(0 0 25px rgba(30,144,255,0.45));
      opacity:0; transform:scale(1.18);
      animation: pubgFade 3.6s cubic-bezier(.2,.9,.2,1) forwards;
    }

    @keyframes pubgFade {
      0% { opacity:0; transform:scale(1.4); filter:blur(10px); }
      55%{ opacity:1; transform:scale(1.03); filter:blur(2px); }
      100%{ opacity:1; transform:scale(1); filter:blur(0); }
    }

    .card-centered {
      width:94%; max-width:760px; margin:0 auto; text-align:center;
      padding:20px 22px; border-radius:14px; border:1px solid rgba(255,255,255,0.04);
    }

    h1 { margin:6px 0 10px 0; color:var(--primary); }

    .loading-bar {
      width:90%; max-width:620px; height:10px;
      background:rgba(255,255,255,0.06); border-radius:999px;
      margin:14px auto; overflow:hidden; border:1px solid rgba(255,255,255,0.03);
    }

    .loading-fill {
      height:100%; width:0%;
      background:linear-gradient(90deg,var(--accent),var(--primary));
      box-shadow:0 6px 26px rgba(30,144,255,0.16);
      border-radius:inherit;
      animation: fillAnim 3s linear forwards;
    }

    @keyframes fillAnim { from{width:0%} to{width:100%} }

    #getButton {
      display:none; margin-top:16px; padding:12px 22px; border-radius:999px; border:none;
      background:linear-gradient(90deg,var(--accent),var(--primary));
      color:#021; cursor:pointer; font-weight:600;
      box-shadow:0 10px 40px rgba(0,188,212,0.12);
    }

    .small { font-size:0.95rem; color:rgba(230,247,251,0.84); }

    /* Ad containers (tight spacing near card) */
    .ad-container {
      display:flex; justify-content:center; align-items:center;
      margin:6px 0;
    }

    /* Popup Ad */
    #popupAd {
      display:none; position:fixed; top:0; left:0; width:100%; height:100%;
      background:rgba(0,0,0,0.7); z-index:9999; justify-content:center; align-items:center;
      animation: fadeIn 0.3s ease forwards;
    }
    #popupAd .ad-box {
      position:relative; background:#fff; padding:10px; border-radius:12px;
      box-shadow:0 0 15px rgba(0,0,0,0.3);
      transform:scale(0.8); opacity:0;
      animation: zoomIn 0.4s ease forwards;
    }
    @keyframes fadeIn { from{opacity:0;} to{opacity:1;} }
    @keyframes zoomIn { to{transform:scale(1); opacity:1;} }

    #closeAd {
      position:absolute; top:-25px; right:8px; background:#fff; color:#000;
      border:none; border-radius:3px; cursor:pointer; padding:2px 6px; font-weight:bold;
    }

    @media (max-width:600px) {
      .logo { width:120px; margin-top:60px; }
      .top-nav { padding:8px 12px; }
      .top-nav a { font-size:0.9rem; }
      .ad-container { margin:4px 0; }
    }
  </style>
</head>
<body>
  <div class="page-bg"></div>

  <!-- Top Navigation -->
  <div class="top-nav">
    <div>
      <a href="{{ url_for('home') }}">🏠 Home</a>
      <a href="{{ url_for('files_list') }}">📁 Files List</a>
      <a id="backBtn" href="#" style="display:none;">← Back</a>
    </div>
  </div>

  <!-- Top Ad (tight above card) -->
  <div class="ad-container" style="margin-top:58px;">
    <script type="text/javascript">
      atOptions = {
        'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
        'format' : 'iframe',
        'height' : 50,
        'width' : 320,
        'params' : {}
      };
    </script>
    <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
  </div>

  <!-- Main Card -->
  <div class="center-full container" aria-live="polite" style="margin-top:0;">
    <div class="card-centered card">
      <img src="/static/logo.png" class="logo" alt="Logo" />
      <h1>{{ file_name }}</h1>
      <div class="small">Preparing your file — please wait</div>

      <div class="loading-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="loading-fill" id="loadingFill"></div>
      </div>

      <a id="fileLink" href="https://t.me/{{ bot_username }}?start=file_{{ msg_id }}">
        <button id="getButton" aria-hidden="true">📥 Get File</button>
      </a>

      <div class="small" style="margin-top:12px; color:rgba(230,247,251,0.6)">
        If the button doesn't appear after a few seconds, try refreshing.
      </div>

      
    </div>
  </div>

  <!-- Bottom Ad (tight below card) -->
  <div class="ad-container" style="margin-bottom:12px;">
    <script type="text/javascript">
      atOptions = {
        'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
        'format' : 'iframe',
        'height' : 50,
        'width' : 320,
        'params' : {}
      };
    </script>
    <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
  </div>

  <!-- Popup Ad -->
  <div id="popupAd">
    <div class="ad-box">
      <button id="closeAd">X</button>
      <script type="text/javascript">
        atOptions = {
          'key' : '798f099ab777961c4eee87794ca29801',
          'format' : 'iframe',
          'height' : 600,
          'width' : 160,
          'params' : {}
        };
      </script>
      <script type="text/javascript" src="//www.highperformanceformat.com/798f099ab777961c4eee87794ca29801/invoke.js"></script>
    </div>
  </div>

<script>
  const loadingFill = document.getElementById('loadingFill');
  const getBtn = document.getElementById('getButton');
  const popupAd = document.getElementById('popupAd');
  const closeAd = document.getElementById('closeAd');
  const fileLink = document.getElementById('fileLink');

  loadingFill.addEventListener('animationend', () => {
    getBtn.style.display = 'inline-block';
    getBtn.style.opacity = 0;
    getBtn.style.transform = 'translateY(6px)';
    setTimeout(()=> {
      getBtn.style.transition = 'opacity .25s ease, transform .25s ease';
      getBtn.style.opacity = 1;
      getBtn.style.transform = 'translateY(0)';
      getBtn.removeAttribute('aria-hidden');
    }, 60);
  });

  // --- Popup on click ---
  getBtn.addEventListener('click', (e) => {
    e.preventDefault();
    popupAd.style.display = 'flex';
    setTimeout(() => {
      popupAd.style.display = 'none';
      window.location.href = fileLink.href;
    }, 1000);
  });

  closeAd.addEventListener('click', () => {
    popupAd.style.display = 'none';
  });

  // Disable context menu & inspect
  document.addEventListener('contextmenu', e => e.preventDefault());
  document.addEventListener('keydown', e => {
    if (e.key === 'F12' || (e.ctrlKey || e.metaKey) &&
      (['U','S','P'].includes(e.key.toUpperCase()) ||
      (e.shiftKey && ['I','J','C','K'].includes(e.key.toUpperCase()))))
      e.preventDefault();
  });

  // --- Show Back button only if came from files list ---
  const backBtn = document.getElementById('backBtn');
  if (document.referrer.includes('/files')) {
    backBtn.style.display = 'inline-block';
    backBtn.addEventListener('click', (e) => {
      e.preventDefault();
      window.history.back();
    });
  }
</script>
</body>
</html>
"""




# ---------- FILES LIST TEMPLATE (search + server-side pagination + centered ads + readable file size + popup ad on search) ----------
FILES_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <title>Files — page {{ page }}{% if query %} (search: {{ query }}){% endif %}</title>
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="icon" type="image/png" href="/static/favicon.png">
  """ + COMMON_HEAD + """
  <style>
    .top-row { display:flex; gap:12px; align-items:center; justify-content:space-between; margin-bottom:18px; flex-wrap:wrap }
    .search-box { display:flex; gap:8px; align-items:center; flex:1 }
    .search-field { flex:1; padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.06);
                    background:rgba(255,255,255,0.02); color:var(--text); min-width:180px }
    .perpage { color:rgba(230,247,251,0.8); font-size:0.92rem; white-space:nowrap }
    .card-file {
      display:flex; flex-direction:row; gap:12px; align-items:center; justify-content:space-between;
      padding:16px; border-radius:12px; border:1px solid rgba(255,255,255,0.04);
      background:rgba(255,255,255,0.02); transition:transform .2s ease, box-shadow .2s ease;
    }
    .card-file:hover {
      transform:translateY(-4px);
      box-shadow:0 6px 20px rgba(0,188,212,0.12);
    }
    .meta { flex:1; text-align:left }
    .file-name { font-weight:600; color:var(--text); word-break:break-word; font-size:1rem }
    .file-size { font-size:0.9rem; color:rgba(230,247,251,0.7); margin-left:8px; white-space:nowrap }
    .actions { display:flex; gap:8px; align-items:center; flex-shrink:0 }
    .page-btn { padding:10px 16px; border-radius:10px; border:1px solid rgba(255,255,255,0.08);
                background:linear-gradient(90deg,var(--accent),var(--primary)); color:#032; font-weight:600;
                box-shadow:0 4px 18px rgba(0,188,212,0.15); transition:transform .18s ease; }
    .page-btn:hover { transform:translateY(-2px) }
    .page-btn[disabled]{ opacity:0.35; cursor:not-allowed }
    .pagination { display:flex; gap:8px; justify-content:center; margin-top:22px; align-items:center; flex-wrap:wrap }
    .grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)) }
    .ad-container { display:flex; justify-content:center; align-items:center; margin:25px 0; text-align:center; }

    /* Popup Ad Styles */
    #popupAd {
      display:none; position:fixed; top:0; left:0; width:100%; height:100%;
      background:rgba(0,0,0,0.7); z-index:9999; justify-content:center; align-items:center;
      animation: fadeIn 0.3s ease forwards;
    }
    #popupAd .ad-box {
      position:relative; background:#fff; padding:10px; border-radius:12px;
      box-shadow:0 0 15px rgba(0,0,0,0.3);
      transform:scale(0.8); opacity:0;
      animation: zoomIn 0.4s ease forwards;
    }
    @keyframes fadeIn { from{opacity:0;} to{opacity:1;} }
    @keyframes zoomIn { to{transform:scale(1); opacity:1;} }
    #closeAd {
      position:absolute; top:-23px;font-size:20px; right:8px; background:#fff; color:black;
      border:none; border-radius:3px; cursor:pointer; padding:2px 6px;
    }

    /* Responsive tweaks */
    @media(max-width:600px){
      .card-file { flex-direction:column; align-items:flex-start; }
      .file-size { margin-left:0; display:block; margin-top:4px; }
      .actions { width:100%; justify-content:flex-end; }
      .page-btn { width:100%; text-align:center; }
      .search-box { width:100%; }
      .search-field { width:100%; }
      .ad-container { margin:16px 0; }
    }
  </style>
</head>
<body>
  <div class="page-bg"></div>
  <div class="container" role="main">
    <div style="display:flex;align-items:center;gap:18px; margin-bottom:18px; flex-wrap:wrap">
      <a href="{{ url_for('home') }}">
        <img src="/static/logo.png" alt="logo" style="width:64px; cursor:pointer; filter:drop-shadow(0 0 10px rgba(0,188,212,0.55))">
      </a>

      <div>
        <div style="font-size:1.1rem; color:var(--primary); font-weight:600">Files</div>
        <div class="small">Browse stored files (page {{ page }} of {{ total_pages }})</div>
      </div>
      <div style="margin-left:auto">
        {% if page > 1 %}
          <a class="glow-btn" href="{{ url_for('files_list') }}?page={{ page-1 }}{% if query %}&search={{ query | urlencode }}{% endif %}">← Back</a>
        {% else %}
          <a class="glow-btn" href="{{ url_for('home') }}">← Back</a>
        {% endif %}
      </div>

    </div>

    <!-- Top Ad -->
    <div class="ad-container">
      <script type="text/javascript">
        atOptions = {
          'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
          'format' : 'iframe',
          'height' : 50,
          'width' : 320,
          'params' : {}
        };
      </script>
      <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
    </div>

    <div class="card">
      <div class="top-row">
        <form id="searchForm" method="get" action="{{ url_for('files_list') }}" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; width:100%">
          <div class="search-box">
            <input class="search-field" name="search" placeholder="Search file names..." value="{{ query | e }}">
            <button class="page-btn" type="submit">Search</button>
          </div>
          <div class="perpage">Showing {{ per_page }} per page</div>
        </form>
      </div>

      <div class="grid">
        {% if files %}
          {% for f in files %}
            <div class="card-file">
              <div class="meta">
                <div class="file-name">
                  {{ f.get('file_name', 'Unnamed File') }}
                  {% if f.get('file_size') %}
                    {% set size = f.get('file_size')|int %}
                    {% if size < 1024 %}
                      <span class="file-size">({{ size }} B)</span>
                    {% elif size < 1048576 %}
                      <span class="file-size">({{ '%.1f' % (size / 1024) }} KB)</span>
                    {% elif size < 1073741824 %}
                      <span class="file-size">({{ '%.1f' % (size / 1048576) }} MB)</span>
                    {% else %}
                      <span class="file-size">({{ '%.2f' % (size / 1073741824) }} GB)</span>
                    {% endif %}
                  {% endif %}
                </div>
              </div>
              <div class="actions">
                <a class="page-btn" href="{{ url_for('redirect_page') }}?id={{ f.get('message_id') }}">Get</a>
              </div>
            </div>
          {% endfor %}
        {% else %}
          <div class="small" style="padding:20px">No files found.</div>
        {% endif %}
      </div>

      <div class="pagination">
        {% if page > 1 %}
          <a class="page-btn" href="{{ url_for('files_list') }}?page={{ page-1 }}{% if query %}&search={{ query | urlencode }}{% endif %}">Previous</a>
        {% else %}
          <button class="page-btn" disabled>Previous</button>
        {% endif %}

        <div class="small">Page {{ page }} / {{ total_pages }}</div>

        {% if page < total_pages %}
          <a class="page-btn" id="nextBtn" href="{{ url_for('files_list') }}?page={{ page+1 }}{% if query %}&search={{ query | urlencode }}{% endif %}">Next</a>
        {% else %}
          <button class="page-btn" disabled>Next</button>
        {% endif %}
      </div>
    </div>

    <!-- Bottom Ad -->
    <div class="ad-container">
      <script type="text/javascript">
        atOptions = {
          'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
          'format' : 'iframe',
          'height' : 50,
          'width' : 320,
          'params' : {}
        };
      </script>
      <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
    </div>

    <!-- Popup Ad -->
    <div id="popupAd">
      <div class="ad-box">
        <button id="closeAd">X</button>
        <script type="text/javascript">
          atOptions = {
            'key' : 'fdf3bc4ff7c8fb37b011cb27d58ecc67',
            'format' : 'iframe',
            'height' : 250,
            'width' : 300,
            'params' : {}
          };
        </script>
        <script type="text/javascript" src="//www.highperformanceformat.com/fdf3bc4ff7c8fb37b011cb27d58ecc67/invoke.js"></script>
      </div>
    </div>

    <script>
    const nextBtn = document.getElementById('nextBtn');
    const popupAd = document.getElementById('popupAd');
    const closeAd = document.getElementById('closeAd');
    const searchForm = document.getElementById('searchForm');

    // Show popup every 3 pages
    if (nextBtn) {
      nextBtn.addEventListener('click', function(event) {
        event.preventDefault();
        let adCount = parseInt(localStorage.getItem('adCount') || '0');
        adCount++;
        if (adCount >= 3) {
          popupAd.style.display = 'flex';
          localStorage.setItem('adCount', 0);
          closeAd.onclick = () => {
            popupAd.style.display = 'none';
            window.location.href = nextBtn.href;
          };
        } else {
          localStorage.setItem('adCount', adCount);
          window.location.href = nextBtn.href;
        }
      });
    }

    // Show popup after search submit
    if (searchForm) {
      searchForm.addEventListener('submit', function(e) {
        e.preventDefault();
        popupAd.style.display = 'flex';
        closeAd.onclick = () => {
          popupAd.style.display = 'none';
          searchForm.submit();
        };
      });
    }
    </script>

  </div>
</body>
</html>
"""







# ---------- Routes ----------

@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/redirect')
def redirect_page():
    # 'id' query param -> message_id
    msg_id = request.args.get('id', default=None)
    if not msg_id:
        # fallback to bot homepage if no id
        return redirect(f"https://t.me/{BOT_USERNAME}")

    # fetch entry (safe)
    try:
        msg_int = int(msg_id)
    except Exception:
        return redirect(f"https://t.me/{BOT_USERNAME}")

    file_entry = files_collection.find_one({"message_id": msg_int}) or {}
    file_name = file_entry.get('file_name') or "Requested File"

    return render_template_string(REDIRECT_TEMPLATE,
                                  msg_id=msg_int,
                                  bot_username=BOT_USERNAME,
                                  file_name=file_name)

@app.route('/files')
def files_list():
    """
    Server-side search + pagination.
    Query params:
      - page (int, 1-based)
      - search (string)
    """
    # pagination settings
    try:
        page = max(1, int(request.args.get('page', 1)))
    except Exception:
        page = 1
    per_page = 10

    search_q = request.args.get('search', '').strip()
    mongo_filter = {}
    if search_q:
        # perform case-insensitive substring search on file_name
        # use regex anchored anywhere (escape special chars)
        import re
        safe_q = re.escape(search_q)
        mongo_filter = {"file_name": {"$regex": safe_q, "$options": "i"}}

    total_count = files_collection.count_documents(mongo_filter)
    total_pages = max(1, ceil(total_count / per_page))
    if page > total_pages:
        page = total_pages

    skip = (page - 1) * per_page

    # fetch results sorted by newest (if message_id correlates with time); adjust sort if you have timestamp
    cursor = files_collection.find(mongo_filter).sort("message_id", DESCENDING).skip(skip).limit(per_page)
    files = list(cursor)

    return render_template_string(FILES_TEMPLATE,
                                  files=files,
                                  page=page,
                                  per_page=per_page,
                                  total_pages=total_pages,
                                  query=search_q,
                                  bot_username=BOT_USERNAME)

# ---------- Run (flask + your telegram client) ----------
def run_flask():
    # accessible on all interfaces; change host/port if needed
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    client.run()
