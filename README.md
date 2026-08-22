# skipera
<img width="96" height="96" alt="image" src="https://github.com/user-attachments/assets/8cf9428c-ef58-45b2-8fff-184ae353a890" />

Module to facilitate skipping Coursera (https://www.coursera.org/) videos and assessments.

## Why?
Skipera assists in automatically skip irrelevant MOOC courses which are made mandatory by universities.
Many of such courses are allotted directly by the university as credit fillers and are not in the interest of the student. The progress of the completion of these courses is tracked by the university and credits are allotted.

## How?
Skipera makes use of the Coursera web API and completes the videos + reading materials.
Graded assessments are completed with the assistance of an LLM API.

## Installation

```bash
pip install skipera
```

Or install from source:

```bash
git clone https://github.com/serv0id/skipera
cd skipera
pip install .
```

## Configuration

On first run, skipera creates a config file at `~/.skipera/config.json`.

### Cookies (automatic)

If you're logged into Coursera in your browser (Chrome, Firefox, or Edge), skipera will automatically fetch the required cookies. Just run the command and it handles the rest. Expired cookies are also re-fetched automatically.

> **Note:** On Windows, Chrome must be closed for cookie fetching to work. On macOS, you may see a Keychain access prompt.

### Cookies (manual)

If automatic fetching doesn't work, you can manually add your cookies to the config file:

```json
{
  "cookies": {
    "CAUTH": "...",
    "CSRF3-Token": "...",
    "__204u": "..."
  }
}
```

To find your cookies, follow the instructions given at https://github.com/serv0id/skipera/issues/1.

## Usage

```bash
skipera course-slug
```

Where `course-slug` is from the Coursera URL. For example, if the URL is `https://www.coursera.org/learn/introduction-psychology/home/module/2`, run:

```bash
skipera introduction-psychology
```

## LLM Support

To solve graded assignments automatically, add an API key for any supported provider to `~/.skipera/config.json` and use the `--llm` flag:

```bash
skipera introduction-psychology --llm
```

### Supported providers

| Provider | Config key | Default model |
|---|---|---|
| Perplexity | `perplexity_api_key` | `sonar-pro` |
| OpenAI | `openai_api_key` | `gpt-4o` |
| Anthropic | `anthropic_api_key` | `claude-3-5-sonnet-latest` |
| Nvidia | `nvidia_api_key` | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| Gemini | `gemini_api_key` | `gemini-3.1-flash-lite` |

You can override the default model for any provider by setting the corresponding `*_model` key in the config (e.g. `"openai_model": "gpt-4.1-mini"`).

If multiple API keys are present, the first one found in the order listed above is used.

> **Note:** An average 10-question assignment consumes ~5000 input tokens. You might not always achieve passing marks due to LLM hallucinations.
