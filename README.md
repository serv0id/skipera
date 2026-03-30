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

If you wish to solve graded assignments automatically, add your Perplexity or Gemini API key to the config file and use the `--llm` flag:

```bash
skipera introduction-psychology --llm
```

Note that an average 10 question assignment consumes ~5000 input tokens. If you wish to use another LLM through an API, please feel free to make a pull request or contact me.

Currently, only the single-choice and multiple-choice objective questions are supported in this mode. Note that you might
not always achieve passing marks due to the LLM hallucinating sometimes.
