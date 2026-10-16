# MD Creator

MD Creator turns documents into Markdown an LLM can read. Headings, lists, tables, and links stay in the output. The file is not summarized, so the words of the document remain. Markdown is usually shorter than the HTML, Office XML, or raw extract you would otherwise paste into a model.

The app shows estimated token counts for the source and the Markdown, saves each conversion in History, and can describe pictures with a vision model so visual detail is not dropped.

## What you can convert

Each file must be 25 MB or smaller.

| Extension | Treated as |
| --- | --- |
| `.pdf` | PDF |
| `.docx` | Word |
| `.pptx` | PowerPoint |
| `.xlsx`, `.xls` | Excel |
| `.html`, `.htm` | HTML |
| `.csv` | CSV |
| `.json` | JSON |
| `.xml` | XML |
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, `.tif`, `.tiff` | Image |

Other types are rejected. The app converts only the bytes you upload or pass on the command line. It does not open URLs.

## How token savings are counted

Counts use the `cl100k_base` tokenizer and are estimates, not a bill from a specific model.

| Input | What "source tokens" means |
| --- | --- |
| HTML, CSV, JSON, XML | The original file text |
| Word, PowerPoint, `.xlsx` | The Office XML inside the file |
| `.xls` | A cell-by-cell dump of the workbook |
| PDF | The raw text extracted from the PDF |
| Images | No text baseline. Savings show as kept context. The description is the Markdown. |

A positive savings percent means the Markdown is shorter than that baseline. A negative percent means the Markdown is longer, which can happen when a compact file becomes a table. Images report the description's token count and do not invent a source count.

Pictures, including pictures inside a PDF or an Office file, are described with the vision model in `LLMHUB_MODEL`. The description asks for visible text, numbers, labels, and relationships, and it asks the model not to omit details. If the model name is missing or the call fails, the document text is still converted and the app shows a warning. Animated or multi-frame images use the first frame.

## Requirements

- Windows PowerShell
- Python 3.11, available on this machine as `py -3`

The `python` command is the Microsoft Store alias and does not run. Use `py -3` or the virtual environment's `python.exe`, as shown below.

You also need an LLM Hub key if you want picture descriptions, and a Supabase project if you want History. Conversion itself still works when those are unset: picture descriptions are skipped, and History shows a warning instead of saving.

## Setup

Open PowerShell in this folder.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and fill in the values below. `.env.example` lists the names. Do not commit `.env` or `.env.doc`. Both are listed in `.gitignore`.

| Variable | Purpose |
| --- | --- |
| `LLMHUB_API_KEY` | Key for the LLM Hub. Used only on the server, for picture descriptions. |
| `LLMHUB_BASE_URL` | OpenAI-compatible base URL. The example value is `https://llmhub.platforms.pfizer/v1`. |
| `LLMHUB_MODEL` | Vision model that accepts image input. The example value is `gpt-4.1`. |
| `SUPABASE_URL` | Supabase project URL. The server uses this with the secret key to read and write History. |
| `SUPABASE_SECRET_KEY` | Server-side Supabase key. The browser never receives it. |
| `SUPABASE_DATABASE_URL` | Postgres connection string. On startup the app creates the `conversions` table if it is missing. |
| `PUBLIC_SUPABASE_URL` | Unused by this app. |
| `PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Unused by this app. |

The browser talks only to the local FastAPI server. History stores the file name, extension, Markdown, token counts, savings percent, any warning, and the time. The original file is not stored.

The `conversions` table has row level security enabled and no public policies. Access goes through the secret key on the server.

## Run the web app

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave that window open, then go to http://127.0.0.1:8000.

1. Drop a file onto the box, or click the box and choose a file. The label changes to the file name and **Convert** becomes available.
2. Click **Convert**. Large files and picture descriptions take longer than a plain HTML file.
3. Read the three cards: source tokens, Markdown tokens, and savings. The savings figure is the percent change. **Kept** means the file had no text baseline, which is the image case.
4. **Preview** shows the rendered document. **Markdown** shows the raw text you would send to a model.
5. **Download** saves a `.md` file with the same name as the upload.
6. **History** on the left lists recent conversions. Click a row to open it again. **Refresh** reloads the list.

A yellow banner is a warning, not a failed conversion. Typical warnings: the vision model was not set, the picture call failed, only the first frame was described, or History could not be saved. The Markdown is still on the page, and Download falls back to that text when History has no id.

Stop the server with Ctrl+C in the PowerShell window.

## Use the command line

Run commands from this folder so Python can import `app`.

Write Markdown to a file and print the stats:

```powershell
.\.venv\Scripts\python.exe -m app.cli report.pdf -o report.md
```

Print Markdown in the terminal. Stats go to the error stream, so you can redirect the document without mixing in the counts:

```powershell
.\.venv\Scripts\python.exe -m app.cli report.pdf > report.md
```

Skip History:

```powershell
.\.venv\Scripts\python.exe -m app.cli report.pdf -o report.md --no-save
```

Stats look like this:

```text
report.pdf
Source tokens: 12,400
Markdown tokens: 3,102
Savings: 75.0%
```

For an image, the source line is `Source tokens: none (no text baseline)` and savings is `context captured`.

A missing path or an unsupported type prints the reason and exits with code 1. If History cannot be reached, the Markdown is still written and the command prints `Warning: the conversion was not saved to history.`

## Check the converter

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_converter.py
```

The HTML fixture checks that the heading, table, and link survive, and that the Markdown token count is lower than the HTML.
