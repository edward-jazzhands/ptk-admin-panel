# Flask + Jinja + HTMX to React Migration Guide

## Current Architecture Overview

Your app follows a traditional server-side rendering pattern with HTMX for dynamic updates:
- **Flask serves HTML pages** (home.html, network.html, git.html)
- **HTMX makes requests** to API endpoints that return **HTML fragments** (partials)
- **Server-side templating** with Jinja2 renders all HTML
- **Auto-polling** with `hx-trigger="load, every 5s"` for live updates

---

## What Needs to Change for React

### 1. Backend API Changes (Most Important)

**Current state:** Your `/api/*` routes in `api.py` return **rendered HTML** via `render_template()`

**What needs to change:**
- All API routes must return **JSON data** instead of HTML
- Remove all `render_template()` calls from `api.py`
- Return serialized Python objects as JSON using `jsonify()`

**Example transformation:**
```python
# CURRENT (api.py:86-89)
@api.route("/api/ssh-status")
def ssh_status() -> str:
    status = util_funcs.get_ssh_status()
    return render_template("partials/_ssh_status.html", context=status)

# NEEDS TO BECOME:
@api.route("/api/ssh-status")
def ssh_status():
    status = util_funcs.get_ssh_status()
    return jsonify(status)  # Return pure JSON
```

This applies to all endpoints:
- `/api/connections` (line 36)
- `/api/conn-info` (line 61)
- `/api/ssh-status` (line 85)
- `/api/modified-files` (line 92)
- `/api/zombies` (line 101)
- `/api/uptime` (line 108)
- `/api/tmux` (line 115)
- `/api/git` (line 122)

---

### 2. Templates Folder - Complete Removal

**What happens:**
- Delete entire `/templates` folder (including `partials/`)
- All HTML rendering logic moves to React components
- Jinja templating syntax (`{% %}`, `{{ }}`) gets replaced with JSX

---

### 3. New React Frontend Structure

**What you need to add:**

```
ptk-admin-panel/
├── src/
│   └── ptk_admin_panel/        # Flask backend (stays)
│       ├── api.py               # Modified to return JSON
│       ├── app.py               # Modified for API-only mode
│       └── views.py             # Probably removed or simplified
└── frontend/                     # NEW React app
    ├── package.json
    ├── src/
    │   ├── App.jsx              # Main React component
    │   ├── main.jsx             # React entry point
    │   ├── components/
    │   │   ├── SSHStatus.jsx    # Replaces _ssh_status.html
    │   │   ├── Connections.jsx  # Replaces _connections.html
    │   │   ├── TmuxStatus.jsx   # Replaces _tmux.html
    │   │   ├── Uptime.jsx       # Replaces _uptime.html
    │   │   ├── Zombies.jsx      # Replaces _zombies.html
    │   │   └── etc...
    │   ├── pages/
    │   │   ├── Home.jsx         # Replaces home.html
    │   │   ├── Network.jsx      # Replaces network.html
    │   │   └── Git.jsx          # Replaces git.html
    │   └── styles/
    │       └── App.css          # Replaces style.css
    └── vite.config.js           # Build tool config
```

---

### 4. Flask App Modifications

**views.py** - Two options:

**Option A:** Keep Flask serving the React app
```python
@views.route("/")
def home():
    return send_from_directory('frontend/dist', 'index.html')
```

**Option B:** Fully decouple (recommended)
- Remove `views.py` entirely
- Run React dev server separately (Vite on port 3000)
- Flask only serves API on port 5000
- Add CORS support to Flask for cross-origin requests

**app.py** needs:
```python
from flask_cors import CORS  # New dependency

app = Flask(__name__)
CORS(app)  # Enable CORS for React dev server
# Remove views blueprint, keep only api
```

---

### 5. HTMX Replacement - React Patterns

**Current HTMX pattern:**
```html
<div
  hx-get="/api/ssh-status"
  hx-trigger="load, every 5s"
  hx-swap="innerHTML"
>
```

**React equivalent:**
```jsx
function SSHStatus() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const fetchStatus = async () => {
      const response = await fetch('/api/ssh-status');
      const data = await response.json();
      setStatus(data);
    };

    fetchStatus(); // Initial load
    const interval = setInterval(fetchStatus, 5000); // Every 5s
    return () => clearInterval(interval); // Cleanup
  }, []);

  return <div>{/* Render status data */}</div>;
}
```

---

### 6. Routing Changes

**Current:** Flask routes in `views.py` (lines 15, 20, 26)

**React replacement:** Client-side routing with React Router
```jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';

<BrowserRouter>
  <Routes>
    <Route path="/" element={<Home />} />
    <Route path="/network" element={<Network />} />
    <Route path="/git" element={<Git />} />
  </Routes>
</BrowserRouter>
```

---

### 7. Navigation Bar

**Current:** Jinja template in `base.html` (lines 16-31)

**React equivalent:** `Navbar.jsx` component
```jsx
import { Link } from 'react-router-dom';

function Navbar() {
  return (
    <nav className="navbar navbar-expand-lg navbar-dark bg-dark">
      <Link className="navbar-brand" to="/">PTK Admin Panel</Link>
      <Link className="nav-link" to="/">Home</Link>
      <Link className="nav-link" to="/network">Network</Link>
      <Link className="nav-link" to="/git">Git</Link>
    </nav>
  );
}
```

---

### 8. Data Serialization Considerations

Some of your Python objects may not serialize to JSON directly:

**In `api.py` (line 40):** You create `MySconn` dataclasses
- These need to be converted to dicts: `asdict(my_sconn)` from `dataclasses`
- Or use `jsonify()` which handles basic dataclasses

**psutil objects:** May need manual conversion
```python
# Instead of passing raw psutil objects:
connections = [
  {
    'name': c.name,
    'pid': c.pid,
    'status': c.status,
    # ... etc
  } for c in conns_list
]
return jsonify(connections)
```

---

### 9. Styling Migration

**Current:** Bootstrap + custom CSS in `style.css`

**React options:**
1. **Keep Bootstrap:** Import in React (`npm install bootstrap`)
2. **Use React Bootstrap:** `react-bootstrap` for React-friendly components
3. **Switch to Tailwind/Material-UI:** More React-idiomatic (optional)

Your `style.css` can be imported directly in React:
```jsx
import './styles/style.css';
```

---

### 10. Static Files

**Current:** Flask's `static/` folder with `style.css`

**React:** Move CSS to `frontend/src/styles/`, bundled by Vite

---

### 11. Development Workflow Changes

**Current:**
- Run Flask server
- Templates auto-reload

**With React:**
- Run Flask backend: `python -m ptk_admin_panel` (port 5000)
- Run React dev server: `npm run dev` (port 3000)
- React proxy requests to Flask or use CORS
- Production: Build React (`npm run build`), serve from Flask

---

### 12. Dependencies to Add

**Python (add to pyproject.toml):**
```toml
"flask-cors>=4.0.0",  # For cross-origin requests
```

**JavaScript (new package.json):**
```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.20.0",
    "bootstrap": "^5.3.0"  // if keeping Bootstrap
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0"
  }
}
```

---

### 13. Authentication Considerations

Your `auth.py` is currently a placeholder. For React:
- Implement JWT or session-based auth in Flask
- Store tokens in React (localStorage or httpOnly cookies)
- Protected routes in React Router
- API calls include auth headers

---

## Summary: Core Changes

1. ✅ **Backend:** Change all `/api/*` routes from `render_template()` to `jsonify()`
2. ✅ **Remove:** Entire `/templates` folder
3. ✅ **Add:** New `/frontend` directory with React app
4. ✅ **Replace:** HTMX polling with React `useEffect` + `setInterval`
5. ✅ **Replace:** Flask routing with React Router
6. ✅ **Replace:** Jinja templating with JSX components
7. ✅ **Add:** CORS support to Flask
8. ✅ **Build:** Vite for bundling React app
9. ✅ **Deploy:** Build React to static files, serve from Flask or separate

---

## The Good News

Your backend logic in `util_funcs/` doesn't need to change at all. The Flask API structure stays the same (same routes), you're just changing what they return (JSON instead of HTML).
