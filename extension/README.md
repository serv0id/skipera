# Skipera Chrome Extension

The Skipera Chrome Extension is a zero-setup, privacy-first tool that solves Coursera quizzes and assignments directly in your browser using AI.

By running entirely within Chrome, it eliminates the need to install Python, run scripts, or manually extract session cookies.

## Features

- **Full Course Automation**: Skip videos, auto-read supplements, and solve quizzes across an entire course with a single click.
- **Zero Configuration**: No `.env` files or session cookie extraction needed. It uses your active Coursera login session.
- **Privacy-First**: The extension runs locally. Your API key is stored securely in your browser's local storage (`chrome.storage.local`).
- **NVIDIA NIM Integration**: Connects directly to NVIDIA's high-performance API to evaluate and solve complex quizzes.
- **Intelligent Retry Logic**: Caches partial correctness and logically deduces the correct combination for complex multi-select questions.
- **Multi-Provider & Key Stacking**: Supports NVIDIA, OpenAI, Anthropic, and Gemini. Stack multiple comma-separated keys to enable concurrent solving and automatic fallback when hitting rate limits (429) or out of credits. *(Tip: Use only one key for normal usage!)*

## Installation (Developer Mode)

Currently, the extension must be loaded as an "Unpacked Extension" in Developer Mode.

1. Clone this repository to your local machine:
   ```bash
   git clone https://github.com/yamantaka-singh/skipera.git
   ```
2. Open Google Chrome and navigate to `chrome://extensions/`.
3. Enable **Developer mode** using the toggle switch in the top right corner.
4. Click the **Load unpacked** button in the top left.
5. Select the `extension/` folder inside the cloned `skipera` repository.
6. The Skipera extension icon should now appear in your browser toolbar!

## Usage

1. **Get an API Key**: Ensure you have an active NVIDIA API key (from `build.nvidia.com`).
2. **Configure the Extension**:
   - Click the Skipera icon in your Chrome toolbar.
   - Enter your **NVIDIA API Key**.
   - Select your preferred model (e.g., `Nemotron 3 Ultra 550B`).
3. **Solve a Quiz**:
   - Navigate to an active Coursera quiz or assignment page (e.g., `https://www.coursera.org/learn/.../exam/.../assessment`).
   - Open the Skipera extension popup and click **Solve Current Quiz**.
4. **Solve an Entire Course**:
   - Navigate to any page within a Coursera course.
   - Open the Skipera extension popup and click **Solve Entire Course**.
   - The extension will run in the background, sequentially finding uncompleted videos, readings, and quizzes, processing them automatically while showing progress via a Toast UI.

## Architecture

- **Manifest V3**: Built using the latest Chrome extension standards.
- **Service Worker (`background.js`)**: Orchestrates the full course state machine in the background to prevent interruptions during navigation, and proxies API requests to NVIDIA to bypass Coursera's strict Content Security Policy (CSP).
- **Content Script (`content.js`)**: Injected into Coursera pages to extract course metadata and display progress Toast notifications.
- **Glassmorphism UI (`popup.html/css`)**: A sleek, modern popup interface.

## Credits

Developed by **yamantaka-singh** and **serv0id**.

<a href="https://github.com/yamantaka-singh">
  <img src="https://github.com/yamantaka-singh.png" width="50" height="50" style="border-radius:50%; margin-right:10px; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'" alt="yamantaka-singh">
</a>
<a href="https://github.com/serv0id">
  <img src="https://github.com/serv0id.png" width="50" height="50" style="border-radius:50%; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'" alt="serv0id">
</a>

*Check out the [Skipera Parent Repository](https://github.com/serv0id/skipera) for more information.*
