# PixelFed Folder Uploader

Automatically monitor a folder for new images and upload them to your Pixelfed instance.

**GitHub Repository:** https://github.com/ratte/pixelfed-folder-autouploader

## Features

- 📁 Monitors a folder for new image files
- 🚀 Automatically uploads new images to Pixelfed
- 🖼️ Supports JPG, PNG, GIF, and WebP formats
- ⚙️ Simple configuration via environment variables
- 📝 Logging for tracking uploads and errors

## Installation

1. Clone or download this project
2. Install the package:

```bash
pip install -e .
```

Or install dependencies manually:

```bash
pip install watchdog requests python-dotenv
```

## Configuration

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit `.env` and configure your settings:

```
PIXELFED_INSTANCE_URL=https://your-instance.com
PIXELFED_ACCESS_TOKEN=your_access_token
WATCH_FOLDER=./watch
DEFAULT_POST_TEXT=#FotiBox #EventXXX
CC_LICENSE=CC BY-NC-SA 4.0
```

**Configuration Options:**

- `PIXELFED_INSTANCE_URL`: Your Pixelfed instance URL (without trailing slash)
- `PIXELFED_ACCESS_TOKEN`: Your access token (see below for how to obtain)
- `WATCH_FOLDER`: Directory to monitor for new images (default: `./watch`)
- `DEFAULT_POST_TEXT`: (Optional) Default text/tags to add to every post
- `CC_LICENSE`: (Optional) Creative Commons license to add to every post (e.g., `CC BY-NC-SA 4.0`, `CC BY 4.0`, `CC0 1.0`)

### Getting a Pixelfed Access Token

1. Log in to your Pixelfed instance
2. Go to **Settings** → **Applications** (or **Development**)
3. Click **Create New Application**
4. Fill in the application details
5. Copy the generated **Access Token**
6. Paste it into your `.env` file

## Usage

Run the uploader:

```bash
pixelfed-uploader
```

Or run directly with Python:

```bash
python -m pixelfed_uploader.main
```

The application will:
1. Create the watch folder if it doesn't exist
2. Scan for existing images (these won't be uploaded)
3. Monitor the folder for new images
4. Automatically upload any new image files

Press `Ctrl+C` to stop the application.

## Project Structure

```
pixelfed-folder-autouploader/
├── pixelfed_uploader/
│   ├── __init__.py
│   ├── main.py              # Main application with file watcher
│   ├── pixelfed_client.py   # Pixelfed API client
│   └── upload_queue.py      # Upload queue management
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Shared test fixtures
│   ├── test_pixelfed_client.py
│   ├── test_main.py
│   └── test_integration.py
├── pyproject.toml           # Project configuration
├── pytest.ini               # Pytest configuration
├── .env.example             # Example environment variables
├── .gitignore
└── README.md
```

## How It Works

1. **File Monitoring**: Uses `watchdog` library to monitor the specified folder
2. **Image Detection**: Detects new image files based on file extension
3. **Upload**: Uses Pixelfed API to upload media and create posts
4. **Tracking**: Keeps track of processed files to avoid duplicates

## Development

### Running Tests

Install test dependencies:

```bash
pip install -e ".[test]"
```

Run all tests:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=pixelfed_uploader --cov-report=html
```

Run specific test files:

```bash
pytest tests/test_pixelfed_client.py
pytest tests/test_main.py
pytest tests/test_integration.py
```

Run tests with verbose output:

```bash
pytest -v
```

### Test Structure

- `tests/test_pixelfed_client.py` - Unit tests for the Pixelfed API client
- `tests/test_main.py` - Unit tests for file handler and main application logic
- `tests/test_integration.py` - Integration tests for end-to-end workflows
- `tests/conftest.py` - Shared fixtures and test configuration

## License

GNU General Public License v3.0
