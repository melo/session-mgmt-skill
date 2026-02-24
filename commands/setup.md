Install all system dependencies required by the session management skill.

No arguments required.

## Steps

### 1. Install Python packages system-wide

```bash
sudo uv pip install --system weasyprint markdown
```

If `uv` is not available, fall back to:
```bash
pip install weasyprint markdown
```

### 2. Install system dependencies for WeasyPrint

WeasyPrint needs pango, cairo, and gdk-pixbuf. Install them based on the detected OS:

**Debian/Ubuntu:**
```bash
sudo apt-get update && sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
```

**Alpine:**
```bash
sudo apk add pango gdk-pixbuf
```

**macOS (Homebrew):**
```bash
brew install pango gdk-pixbuf
```

Detect the OS automatically and run the appropriate command. If the dependencies are already installed, the package manager will skip them.

### 3. Verify installation

```bash
/usr/local/bin/python3 -c "import weasyprint; import markdown; print('All dependencies installed successfully')"
```

If this fails, report the error to the user.

### 4. Report

Print a summary:

| Dependency | Status |
|------------|--------|
| `weasyprint` | Installed / Already present |
| `markdown` | Installed / Already present |
| System libs (pango, cairo) | Installed / Already present |
