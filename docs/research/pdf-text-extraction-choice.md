# PDF text extraction for the arq worker: library and OCR fallback choice

Date of research: 2026-09-14. Every claim carries the URL it was read from. Unless marked
**(secondary)**, a source is the vendor's own pricing/docs page, an official GitHub README, or a
PyPI page. Numbers marked **(estimate)** are computed here from official unit prices and stated
assumptions, not quoted from a vendor.

Context recap: Python worker (arq, Docker, small VPS); uploads up to 50 MB; 20-200 documents/month;
PDFs are either text-layer or scanned; language unknown in advance (EN/FR/DE/ES/other); output must
keep page numbers and character offsets; budget near zero for text-layer PDFs, a few dollars/month
for scanned ones.

---

## 1. Recommendation

**Text-layer pages: `pypdfium2`.** BSD-3-Clause / Apache-2.0, ships a prebuilt PDFium wheel with no
mandatory runtime dependencies, exposes per-page text pages with `count_chars()`, `get_text_range()`
and `get_charbox(index)` for per-character bounding boxes, and can render any page to a bitmap at a
chosen DPI for the OCR fallback. No AGPL exposure, no Tesseract build step.

**Scanned-page detection: a per-page, two-signal heuristic in our own code.** Treat a page as
"needs OCR" when the PDFium text page yields fewer than a small number of non-whitespace characters
(we suggest 20, tunable) *and/or* the extracted text is dominated by U+FFFD replacement characters,
and the page contains at least one image object. No official doc publishes a numeric character
threshold; OCRmyPDF's official behaviour is that *any* text object in the content stream marks a
page as "has text", with a detailed mode that only counts text boxes intersecting the interior of
the page (12.5 % margins excluded) and that flags corrupt text via U+FFFD. Our heuristic is a
stricter version of that (source in section 5).

**Scanned-page fallback: one hosted API, Azure AI Document Intelligence `prebuilt-read`.** Reasons:

- Lowest confirmed unit price class ($1.50 per 1,000 pages, see caveat) and a permanent free tier
  (500 pages/month, first 2 pages of each request). Worst case in scope (every one of 4,000
  pages/month scanned) is about $6/month; 500 scanned pages/month is about $0.75 (both **estimate**).
- No language code needed: the model "will auto-detect the text language" and extracts mixed-language
  lines; printed-text support spans a list of ~300 languages including EN/FR/DE/ES; handwriting for
  EN/FR/DE/ES/IT/PT/ZH/JA/KO/RU/TH/AR.
- Output natively carries what we need: `pages[].pageNumber`, per-word `confidence`, and `spans`
  (`offset`, `length`) into a single `content` string, i.e. character offsets for free.
- Single synchronous-poll call per document (up to 500 MB / 2,000 pages on S0), so a 50 MB,
  200-page upload is one request; no object-store staging as with Textract async or Google batch.
- Python SDK `azure-ai-documentintelligence` (MIT).

**Local Tesseract is unnecessary at this volume.** At $1.50 per 1,000 pages, even 100 % scanned
traffic costs ~$6/month; Tesseract would add ~10-15 MB of Debian packages to the image (fine) but
also CPU/RAM pressure on a small VPS, no automatic language detection (you must pass
`eng+fra+deu+spa`, and language order changes output and timing), and a second engine to operate.
Keep `pytesseract` documented as the offline/dev fallback plan; do not ship it in v1.

Runner-up hosted options, in order: AWS Textract (same price, but text detection limited to
EN/FR/DE/IT/PT/ES and >1-page PDFs require the async S3 flow), Google Document AI OCR (same price,
but online requests are capped at 15 pages / 40 MB so our 20-page average forces batch via GCS),
Mistral OCR ($4 per 1,000 pages, simplest API, Markdown per page, ~40 languages). A vision LLM
(Claude Haiku 4.5) is roughly 3x the price of the OCR APIs at the same volume and returns free-form
text without per-word confidence; it remains the right tool for *understanding* pages, not for bulk
OCR.

---

## 2. Comparison tables

### A. Local Python libraries for text-layer PDFs (all read 2026-09-14)

| Library | PyPI name / version | License | Speed claims (official) | Per-page text | Character positions | Notes |
|---|---|---|---|---|---|---|
| pypdfium2 | `pypdfium2` 5.13.0 (2026-08-13) | BSD-3-Clause / Apache-2.0; PDFium BSD-style | None stated | `page.get_textpage()` per page | `get_charbox(index)`, `count_chars()`, `get_text_range()`, `get_index(x,y)` | Prebuilt PDFium wheels; also renders pages (`page.render(scale=...)`) for OCR input |
| PyMuPDF | `pymupdf` 1.28.2 (2026-08-06) | **AGPL-3.0 or Artifex commercial** | 8.01 s vs PDFMiner 227.27 s on 7,031 pages (own benchmark) | `page.get_text("text"/"words"/"dict"/"rawdict")` | `rawdict` gives per-character `c`, `origin`, `bbox` | Fastest, richest API; AGPL is a blocker for a proprietary service unless licensed |
| pdfplumber | `pdfplumber` 0.11.10 (2026-06-15) | MIT | None; "slightly faster" `extract_text_simple()` | `page.extract_text()` | `page.chars` with `x0,x1,top,bottom,text,fontname,size` | Built on pdfminer.six (slowest in PyMuPDF's benchmark); memory note for large PDFs |
| pypdf | `pypdf` 6.18.1 (2026-09-11) | BSD-3-Clause | Pure Python; warns text extraction can need a lot of memory (10 GB case documented) | `page.extract_text()` | Only via `visitor_text(text, user_matrix, tm_matrix, font_dict, font_size)`; "positions may be difficult to determine" | Fine for splitting/merging; weakest for positions |

### B. Local OCR (read 2026-09-14)

| Option | Package | License | Docker image impact | Multi-language / detection | Per-page confidence | GPU |
|---|---|---|---|---|---|---|
| Tesseract 5 via pytesseract | `pytesseract` 0.3.13 (2024-08-16); system `tesseract-ocr` | Apache-2.0 (engine and tessdata_fast models); pytesseract Apache-2.0 | Debian bookworm installed sizes: `tesseract-ocr` 2.1 MB, `libtesseract5` 2.3-4.2 MB, `tesseract-ocr-eng` 4.0 MB, `-fra` 1.1 MB, `-deu` 1.5 MB, `-spa` 2.3 MB (+ leptonica) | `lang='eng+fra+deu+spa'`; no detection; language order affects time and output; `osd` pack for script detection only | Word-level `conf` column from `image_to_data` / TSV | No (CPU) |
| OCRmyPDF | `ocrmypdf` (CLI + `ocrmypdf.ocr()`) | MPL-2.0 | Needs Tesseract + Ghostscript; official image `jbarlow83/ocrmypdf-alpine` is 297 MB compressed and bundles EN/DE/ZH-Hans/FR/PT/ES | `-l eng+fra`; "English is assumed by default unless other language(s) are specified" | Not exposed (produces PDF text layer + `--sidecar` text) | No |
| Docling | `docling` 2.127.0 (2026-09-14) | MIT | PyTorch-based layout models (size not stated on official pages); EasyOCR default, Tesseract/RapidOCR/OcrMac optional | Tesseract options default `["eng","spa","fra","deu"]`; EasyOCR default `["en","es","fr","de"]`; example "Automatic OCR language detection with tesseract" | Not stated on read pages | Optional (`device` cpu/cuda/mps; default 4 CPU threads) |
| Marker | `marker-pdf` | Code Apache-2.0; **models under a modified OpenRAIL-M, free only under $5M funding/revenue** | Deep-learning models (surya) | "multilingual" via surya | Not stated | "GPU, CPU, or MPS"; fast mode for CPU |

### C. Hosted document extraction / OCR APIs (read 2026-09-14)

Volume scenarios: **4,000 pages/month** (200 scanned docs x 20 pages) and **500 pages/month**.
All monthly figures are **estimates** from the listed unit price, ignoring one-off sign-up credits.

| Service | Unit price | Free tier | Limits per request | Languages statement | Page boundaries in output | Python SDK | Rate limits | 4,000 p/mo | 500 p/mo |
|---|---|---|---|---|---|---|---|---|---|
| Mistral OCR (`mistral-ocr-latest`, OCR 4.1) | $4 / 1,000 pages ("OCR"); "Document AI" $5 / 1,000; a separate "OCR (per 1K pages) $3" line under Agent API tools | None stated for OCR | Not stated on docs pages read; file upload max 512 MB (Libraries/Files) | "performs strongly across more than 40 languages" | Yes: `pages[].index`, `pages[].markdown`, `include_blocks` for paragraph bboxes | `mistralai` 2.10.0 | Tiered by billing (free/T1-T4); numbers not published | $16 | $2 |
| LlamaParse (LlamaCloud) | $1.25 / 1,000 credits; Parse tiers Fast 1, Cost-effective 3, Agentic 10, Agentic Plus 45 credits/page | 10K credits/month on Free plan | Platform upload 512 MB; 64 KB text per page; 35 images per page | `language` param; "long list of languages" (v1 docs) | Yes: `result.markdown.pages[i].markdown` | `llama-cloud` 2.16.0 (`llama-cloud-services` deprecated) | Free tier 20 req/min; upload 50 QPS | Fast $5 (free tier covers it); Cost-effective $15; Agentic $50 | Fast $0.63; Cost-eff $1.88; Agentic $6.25 (all inside 10K free credits) |
| Reducto | r-1 Parse $10 / 1,000 pages | $150 sign-up credits (one-off); "No Page Limits" | Uploads up to 5 GB via presigned URL | "60+ languages with automatic language detection" | Yes: block `bbox.page` (1-indexed) and `original_page` | `reductoai` 0.24.0 | 1,000 req/s per key; `/job` 200 req/s | $40 | $5 |
| Unstructured API | $0.015 / page | 10,000 free pages to start (one-off) | Not stated | `languages` list of Tesseract codes | Yes: `starting_page_number` + element metadata; `coordinates` option | `unstructured-client` 0.46.2 | Not stated | $60 | $7.50 |
| Azure AI Document Intelligence Read (`prebuilt-read`) | Official page rendered "$-" (JS); **(secondary)** $1.50 / 1,000 pages 0-1M, $0.60 above 1M | F0: 500 pages/month, only first 2 pages per request, 4 MB max | S0: 500 MB, 2,000 pages | Auto-detects; ~300 printed languages incl. EN/FR/DE/ES; 12 handwritten | Yes: `pages[].pageNumber`, `spans{offset,length}`, per-word `confidence` | `azure-ai-documentintelligence` 1.0.2 (MIT) | S0 default 15 analyze TPS, 50 get TPS | $6 | $0.75 |
| AWS Textract DetectDocumentText | $0.0015 / page first 1M (US West Oregon quoted; US East not on page) | 1,000 pages/month for 3 months (new accounts) | Sync: 10 MB, PDF limited to 1 page; async: 500 MB, 3,000 pages (S3 required) | EN, FR, DE, IT, PT, ES only; handwriting EN only; no language returned | Yes: Block `Page`, LINE/WORD with `Confidence` and `Geometry` | `boto3` | us-east-1: 25 TPS sync, 15 TPS start-async | $6 | $0.75 |
| Google Document AI Enterprise Document OCR | **(secondary, search snippet of official page)** $1.50 / 1,000 pages up to 5M, $0.60 above | None stated | Online: 15 pages, 40 MB; batch: 1 GB via GCS | "more than 200 languages", language detection, hints | Yes: `pages[].pageNumber` (1-based), `textAnchor.textSegments{startIndex,endIndex}` into `document.text`, token confidence | `google-cloud-documentai` 3.15.0 (Apache-2.0) | 1,800 req/min per user; 120 pages/min online (base) | $6 | $0.75 |
| Claude (Haiku 4.5) PDF/image input | $1 / MTok in, $5 / MTok out; batch 50 % off | "small amount of free credits" for new users | 32 MB request, 600 pages (100 on 200k-context models); images 10 MB each, up to 600 per request | Model-level multilingual; no OCR-specific language list | Yes if citations enabled (`page_location`, 1-indexed); otherwise you prompt for page markers | `anthropic` | Usage tiers | ~$20 (~$10 batch) **(estimate)** | ~$2.60 (~$1.30 batch) **(estimate)** |
| OpenAI (gpt-5-mini) PDF/image input | $0.25 / MTok in, $2.00 / MTok out; batch 50 % off | Not stated | Files under 50 MB, 50 MB combined; page cap not stated | Model-level multilingual | Not native; prompt for page markers | `openai` | Usage tiers | ~$8 (~$4 batch) **(estimate)** | ~$1 **(estimate)** |

---

## 3. Per-option details with sources

### A1. pypdfium2

- Package `pypdfium2`, latest 5.13.0 released 2026-08-13, license "BSD-3-Clause, Apache-2.0,
  dependency licenses", Python >= 3.6, no mandatory runtime dependencies (Pillow/NumPy optional).
  https://pypi.org/project/pypdfium2/
- "pypdfium2 itself is available by the terms and conditions of Apache-2.0 / BSD-3-Clause"; PDFium is
  under "a BSD-style license". Wheels bundle a pre-built PDFium.
  https://github.com/pypdfium2-team/pypdfium2
- Text API: `PdfPage.get_textpage()` returns a `PdfTextPage`; `get_text_range(index=0, count=-1)`
  (UCS-2 limited), `get_text_bounded(left, bottom, right, top)` (full Unicode), `count_chars()`,
  `get_charbox(index, loose=False)` returning "left, bottom, right and top in PDF canvas units",
  `get_index(x, y, x_tol, y_tol)`, `count_rects()`/`get_rect(index)`.
  https://pypdfium2.readthedocs.io/en/stable/python_api.html
- Rendering: `PdfPage.render(scale=1, rotation=0, crop=..., ...)`; "To convert a DPI value to a scale
  factor, multiply it by the size of 1 canvas unit in inches (usually 1/72in)". `PdfDocument` accepts
  path, bytes, or a seekable byte stream; `len(doc)` and `doc.get_page(i)` (0-based).
  https://pypdfium2.readthedocs.io/en/stable/python_api.html
- No speed claims on the README or PyPI page. https://github.com/pypdfium2-team/pypdfium2

### A2. PyMuPDF

- Package `pymupdf` 1.28.2 (2026-08-06), "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial
  License", Python 3.10-3.14. PyPI text claims "10-50x speed improvements for text extraction" over
  pure-Python libraries. https://pypi.org/project/PyMuPDF/
- "PyMuPDF and MuPDF are now available under both, open-source AGPL and commercial license
  agreements." Benchmark on 7,031 pages: text extraction PyMuPDF 8.01 s, XPDF 27.42 s, PyPDF2
  101.64 s, PDFMiner 227.27 s. https://pymupdf.readthedocs.io/en/latest/about.html and
  https://pymupdf.readthedocs.io/en/latest/app4.html
- `Page.get_text()` with `"text"`, `"blocks"`, `"words"`, `"dict"`, `"rawdict"`; `rawdict`
  "additional detail down to each character" with `"c"`, `"origin"`, `"bbox"`; `extractWORDS`
  tuples `(x0, y0, x1, y1, "word", block_no, line_no, word_no)`.
  https://pymupdf.readthedocs.io/en/latest/page.html and
  https://pymupdf.readthedocs.io/en/latest/textpage.html
- Integrated OCR: `get_textpage_ocr(language, tessdata, dpi, full)`; "based on Tesseract-OCR which
  must be installed as a separate application"; needs tessdata via `TESSDATA_PREFIX`; can OCR the
  complete page or only image areas. https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html and
  https://pymupdf.readthedocs.io/en/latest/installation.html

### A3. pdfplumber

- Package `pdfplumber` 0.11.10 (2026-06-15), MIT, Python >= 3.8, built on `pdfminer.six`; "Works
  best on machine-generated, rather than scanned, PDFs". https://pypi.org/project/pdfplumber/
- `page.chars` objects carry `x0, x1, top, bottom, text, fontname, size, upright`;
  `extract_text(x_tolerance, y_tolerance, layout, return_chars, use_text_flow)`;
  `extract_words()` returns words with bounding boxes; large PDFs: cached properties "can require a
  lot of memory", call `.close()`. https://github.com/jsvine/pdfplumber

### A4. pypdf

- Package `pypdf` 6.18.1 (2026-09-11), BSD-3-Clause, Python >= 3.9, "pure-python PDF library".
  https://pypi.org/project/pypdf/
- `page.extract_text()`; `visitor_text(text, user_matrix, tm_matrix, font_dictionary, font_size)`
  gives matrices, "in complicated documents, the calculated positions may be difficult to determine";
  `extraction_mode="layout"`; "Extracting the text of a page requires parsing its whole content
  stream. This can require quite a lot of memory" (10 GB case cited).
  https://pypdf.readthedocs.io/en/stable/user/extract-text.html

### B1. Tesseract + pytesseract

- Engine "licensed under the Apache License, Version 2.0"; "can recognize more than 100 languages";
  LSTM engine since Tesseract 4. https://github.com/tesseract-ocr/tesseract
- `pytesseract` 0.3.13 (2024-08-16), Apache-2.0; requires the `tesseract` binary on PATH;
  `image_to_data` returns "box boundaries, confidences, and other information" (word-level `conf`);
  `lang='eng+fra'` for multiple languages; `image_to_pdf_or_hocr`. https://pypi.org/project/pytesseract/
- CLI: `-l LANG[+LANG]`; "The time taken for OCR as well as the output can be different based on the
  order of languages"; TSV output includes a `conf` column; `--psm` modes.
  https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html
- "Tesseract works best on images which have a DPI of at least 300 dpi"; noise should be removed
  before OCR. https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html
- Model repos: `tessdata_fast` ("best value for money in speed vs accuracy, Integer models"),
  `tessdata_best` (float, most accurate, slowest), `tessdata`; `osd` = orientation and script
  detection. https://tesseract-ocr.github.io/tessdoc/Data-Files.html
- tessdata_fast: "All data in the repository are licensed under the Apache-2.0 License".
  https://github.com/tesseract-ocr/tessdata_fast
- Debian bookworm installed sizes: `tesseract-ocr` 5.3.0-2, 2,135 kB (depends on `-eng` and `-osd`)
  https://packages.debian.org/bookworm/tesseract-ocr ; `libtesseract5` 2,321-4,178 kB by arch,
  depends on `liblept5` https://packages.debian.org/bookworm/libtesseract5 ; `tesseract-ocr-eng`
  4,032 kB https://packages.debian.org/bookworm/tesseract-ocr-eng ; `-fra` 1,119 kB
  https://packages.debian.org/bookworm/tesseract-ocr-fra ; `-deu` 1,505 kB
  https://packages.debian.org/bookworm/tesseract-ocr-deu ; `-spa` 2,256 kB
  https://packages.debian.org/bookworm/tesseract-ocr-spa

### B2. OCRmyPDF

- "licensed under the Mozilla Public License 2.0 (MPL-2.0)"; requires Ghostscript and Tesseract
  (4.1.1+). https://github.com/ocrmypdf/OCRmyPDF
- Modes: `--skip-text` "no image processing or OCR will be performed on pages that already have
  text"; `--force-ocr` rasterizes all pages; `--redo-ocr` "detailed text analysis"; default: "If a
  page in a PDF seems to have text, by default OCRmyPDF will exit without modifying the PDF".
  https://ocrmypdf.readthedocs.io/en/latest/advanced.html
- Error text "page already has text! - aborting (use --force-ocr to force OCR)" and the three
  remedies. https://ocrmypdf.readthedocs.io/en/latest/errors.html
- `--sidecar` writes a companion `.txt` containing only OCR-generated text (not pre-existing text).
  https://ocrmypdf.readthedocs.io/en/latest/cookbook.html
- Python API `ocrmypdf.ocr(...)` with `language`, `sidecar`, `skip_text`/`force_ocr`/`redo_ocr`,
  `pages`, `jobs`, `tesseract_timeout`, `output_type` (incl. `'none'`); "Creating a child process to
  call ocrmypdf.ocr() is suggested". https://ocrmypdf.readthedocs.io/en/latest/apiref.html and
  https://ocrmypdf.readthedocs.io/en/latest/api.html
- Languages: `ocrmypdf -l eng+fra`; "English is assumed by default unless other language(s) are
  specified". https://ocrmypdf.readthedocs.io/en/latest/languages.html
- Memory: "budget about 15 bytes per pixel of the largest page, per concurrent job"; a 34 MP page
  (letter at 600 dpi) "peaks at roughly 500 MB with --jobs 1"; Tesseract "peaks at about 12 bytes per
  pixel". https://ocrmypdf.readthedocs.io/en/latest/performance.html
- Docker: `jbarlow83/ocrmypdf-alpine` recommended, x86_64 and arm64, "includes English, German,
  Simplified Chinese, French, Portuguese and Spanish" by default.
  https://ocrmypdf.readthedocs.io/en/latest/docker.html ; latest tag 297 MB compressed
  https://hub.docker.com/r/jbarlow83/ocrmypdf-alpine

### B3. Docling

- MIT; "Advanced PDF understanding incl. page layout, reading order, table structure"; "Extensive OCR
  support for scanned PDFs and images"; Python >= 3.10. https://github.com/docling-project/docling
- `docling` 2.127.0 (2026-09-14), MIT, extras `easyocr`, `tesserocr`, `rapidocr`, `ocrmac`, `vlm`.
  https://pypi.org/project/docling/
- EasyOCR default; `TesseractOcrOptions`, `TesseractCliOcrOptions`, `RapidOcrOptions`,
  `OcrMacOptions`; `do_ocr`, `force_full_page_ocr`; `AcceleratorOptions(device=cpu|cuda|mps,
  num_threads)`; "The default setting is using 4 CPU threads"; `docling-tools models download`.
  https://docling-project.github.io/docling/usage/advanced_options/
- Source defaults: `EasyOcrOptions.lang = ["en","es","fr","de"]`,
  `TesseractOcrOptions.lang = ["eng","spa","fra","deu"]`.
  https://github.com/docling-project/docling/blob/main/docling/datamodel/pipeline_options.py
- RAM/model sizes are not stated on the official pages read (open question).

### B4. Marker

- Code Apache-2.0; models under "modified AI Pubs Open Rail-M license (free for research, personal
  use, and startups under $5M funding/revenue)"; PyPI `marker-pdf`; runs on "GPU, CPU, or MPS"; OCR via
  surya, "multilingual"; `--paginate_output` inserts page separators.
  https://github.com/datalab-to/marker

### C1. Mistral OCR

- API pricing page: OCR 4.1 "OCR: $4 / 1000 pages", "Document AI: $5 / 1000 pages"; Agent API tools
  list "OCR (per 1K pages) $3"; a "Batch" tier "at half price" is described for models (OCR
  applicability not stated). https://mistral.ai/pricing/api
- Model id `mistral-ocr-latest`; response `pages[]` with `index` and `markdown` plus optional images,
  tables, dimensions, confidence, blocks; "Multilingual OCR performs strongly across more than 40
  languages"; SDK `client.ocr.process(model=..., document={...})`.
  https://docs.mistral.ai/studio/document-processing/basic_ocr and
  https://docs.mistral.ai/capabilities/document_ai/basic_ocr/
- Endpoint schema: `pages` selection string (0-based), `include_image_base64`, `table_format`,
  `include_blocks` (paragraph bboxes), `usage_info.pages_processed`; no file-size/page limits stated.
  https://docs.mistral.ai/api/endpoint/ocr
- File uploads: "Maximum file size: 512 MB", OCR formats PDF/PNG/JPG/JPEG/TIFF/BMP/GIF/WEBP.
  https://docs.mistral.ai/resources/known-limitations
- Model catalog: `mistral-ocr-2505` retired 2026-05-31, `mistral-ocr-2503` retired 2025-12-31,
  successor "OCR 4.1". https://docs.mistral.ai/getting-started/models/models_overview/
- Rate limits: RPS, tokens/min, tokens/month, tiered by cumulative billing (free, T1 pay-as-you-go,
  T2 >$20, T3 >$100, T4 >$500); numbers only in the admin console.
  https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them
- SDK `mistralai` 2.10.0 (2026-09-09). https://pypi.org/project/mistralai/
- Cost **(estimate)**: 4,000 x $4/1,000 = $16; 500 pages = $2.

### C2. LlamaParse (LlamaCloud)

- Plans: Free "10K credits" monthly; Starter $50 (40K credits); Pro $500 (400K); "1,000 credits =
  $1.25". https://www.llamaindex.ai/pricing
- "Price per 1,000 Credits" "$1.25"; Parse tier credits/page: Fast 1, Cost-effective 3, Agentic 10,
  Agentic Plus 45 (v2). https://developers.llamaindex.ai/llamaparse/general/pricing/ and
  https://developers.llamaindex.ai/llamaparse/parse/guides/tiers/
- Fast tier: "plain-text documents at high volume where you only need text"; Agentic: "most real-world
  PDFs with tables, scanned pages, multi-column layouts". Whether Fast performs OCR on scanned pages
  is not stated (open question). https://developers.llamaindex.ai/llamaparse/parse/guides/tiers/
- SDK: `llama-cloud>=2.8`; `client.parsing.parse(file_id=..., tier="agentic", version="latest",
  expand=["markdown"])`; per-page `result.markdown.pages[0].markdown`.
  https://developers.llamaindex.ai/llamaparse/parse/getting_started/
- Limits: "Maximum file size: 512MB"; "Maximum text extracted per page: 64KB"; "Maximum images
  extracted per page: 35". https://developers.llamaindex.ai/llamaparse/general/limitations/
- Rate limits: upload 50 QPS, "Free tier organizations have lower rate limits, at 20 requests per
  minute". https://developers.llamaindex.ai/llamaparse/general/rate_limits/
- `llama-cloud` 2.16.0 (2026-09-08), MIT https://pypi.org/project/llama-cloud/ ;
  `llama-cloud-services` 0.6.94 deprecated (maintenance ended 2026-05-01)
  https://pypi.org/project/llama-cloud-services/
- Cost **(estimate)**: Fast 4,000 credits = $5.00 (inside the 10K free credits); Cost-effective
  12,000 credits = $15.00; Agentic 40,000 = $50.00. 500 pages: $0.63 / $1.88 / $6.25 (all inside free).

### C3. Reducto

- "r-1 Parse: $10" per 1,000 pages; "Standard accounts include 15,000 free credits" / "$150 in free
  usage after sign-up"; "No Page Limits". https://reducto.ai/pricing
- Blocks carry `bbox.page` "Page number (1-indexed) in the processed output" and `original_page`,
  `confidence` "high"/"low", `granular_confidence`. https://docs.reducto.ai/parse/response-format.md
- "Process documents in 60+ languages with automatic language detection."
  https://docs.reducto.ai/cookbooks/multilingual-processing.md
- Rate limits: "1,000 req/s sustained" per key; `/job/{id}` "200 req/s".
  https://docs.reducto.ai/reference/rate-limits.md
- SDK `pip install reductoai`; `client.parse.run(input=upload.file_id)`.
  https://docs.reducto.ai/sdk/python/overview.md ; `reductoai` 0.24.0 (2026-09-08), Apache-2.0
  https://pypi.org/project/reductoai/
- Cost **(estimate)**: 4,000 pages $40; 500 pages $5.

### C4. Unstructured API

- "10,000 free pages to start. No card required."; "Pay only $0.015 a page after your first 10,000
  free pages." https://unstructured.io/pricing
- Strategies `auto`, `vlm`, `hi_res`, `fast`, `ocr_only`; `languages`: "The languages present in the
  document, for use in partitioning and OCR" (Tesseract codes); `coordinates` option;
  `starting_page_number` included in element metadata.
  https://docs.unstructured.io/api-reference/partition/api-parameters and
  https://docs.unstructured.io/api-reference/partition/partitioning
- Page counting: "a page is a page, slide, or image: .pdf, .pptx, and .tiff"; Unstructured recommends
  its newer job/pipeline operations over the legacy Partition endpoint.
  https://docs.unstructured.io/api-reference/partition/overview
- SDK `unstructured-client` 0.46.2, MIT. https://pypi.org/project/unstructured-client/
- Cost **(estimate)**: 4,000 x $0.015 = $60; 500 pages $7.50.

### C5. Azure AI Document Intelligence, Read model

- Official pricing page: "0 - 500 pages free per month" (F0); S0 Read rows "0-1M pages - $- per
  1,000 pages" and "1M+ pages - $- per 1,000 pages" (amounts not rendered without JavaScript).
  https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/
- **(secondary)** Read $1.50 per 1,000 pages (0-1M), $0.60 above 1M; Layout $10 per 1,000
  (search-engine summary of the official page and third-party pricing guides, not verified against
  the rendered page). https://azure.microsoft.com/en-us/pricing/details/document-intelligence/
- Service limits: F0 "Max document size 4 MB", "Max number of pages (Analysis) 2"; S0 500 MB, 2,000
  pages; S0 15 analyze TPS, 50 get TPS; "The free tier limits analyze response to only the first two
  pages in a request."; each PDF page = 1 billed page.
  https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits
- Read model: model id `prebuilt-read`; "up to 2,000 pages can be processed"; output `pages[]` with
  `pageNumber`, `words[]` with `confidence` and `span`, `styles[].spans{offset,length}`; `pages` query
  parameter for ranges; searchable PDF output at no added cost.
  https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read
- Languages: "extract all multi-lingual text in your documents, including text lines with mixed
  languages, and don't require specifying a language code"; "will auto-detect the text language";
  printed list includes English `en`, French `fr`, German `de`, Spanish `es`; handwritten EN, ZH-Hans,
  FR, DE, IT, JA, KO, PT, ES, RU, TH, AR.
  https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr
- SDK `azure-ai-documentintelligence` 1.0.2 (2025-03-27), MIT;
  `begin_analyze_document("prebuilt-read", body=f)`. https://pypi.org/project/azure-ai-documentintelligence/
- Cost **(estimate, using the secondary $1.50 figure)**: 4,000 pages $6.00; 500 pages $0.75.

### C6. AWS Textract

- "The pricing per page in US West (Oregon) region for the first one million pages is $0.0015" for
  Detect Document Text; free tier "1,000 pages per month" for three months.
  https://aws.amazon.com/textract/pricing/
- Set quotas: sync "10 MB in memory. PDF and TIFF files also have a limit of 1 page"; async "500 MB in
  memory and a limit of 3,000 pages"; "supports English, French, German, Italian, Portuguese, and
  Spanish text detection. Amazon Textract will not return the language detected"; handwriting English
  only; min text height 15 px. https://docs.aws.amazon.com/textract/latest/dg/limits-document.html
- FAQ: printed text, forms and tables "in English, German, French, Spanish, Italian and Portuguese".
  https://aws.amazon.com/textract/faqs/
- Output: Block objects with lines/words, "The page that the detected text appears on", geometry.
  https://docs.aws.amazon.com/textract/latest/dg/how-it-works-detecting.html
- Default TPS us-east-1: DetectDocumentText 25, StartDocumentTextDetection 15.
  https://docs.aws.amazon.com/general/latest/gr/textract.html
- Cost **(estimate)**: 4,000 pages $6.00; 500 pages $0.75.

### C7. Google Document AI, Enterprise Document OCR

- Official pricing page could not be rendered by the fetch tool (content truncated).
  **(secondary, search snippet of the official page)**: "$1.50 per 1,000 pages for 1-5,000,000 pages
  per month, and $0.60 per 1,000 pages for 5,000,001+", OCR add-ons $6 per 1,000.
  https://cloud.google.com/document-ai/pricing
- Limits: online 15 pages / 40 MB; batch 1 GB, up to 5,000 files per request.
  https://docs.cloud.google.com/document-ai/limits
- "identify and extract text, including handwritten text, from documents in more than 200 languages";
  EN/FR/DE/ES listed. https://docs.cloud.google.com/document-ai/docs/languages
- "Language detection: Detects the languages used in the extracted texts"; language hints via BCP-47.
  https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr
- Response: `document.text` single string; `textAnchor.textSegments{startIndex,endIndex}`;
  "pageNumber is 1-based"; token confidence. https://docs.cloud.google.com/document-ai/docs/handle-response
- Quotas: "Requests per minute 1,800 per user"; 120 pages/min online (base).
  https://docs.cloud.google.com/document-ai/quotas
- SDK `google-cloud-documentai` 3.15.0 (2026-06-03), Apache-2.0.
  https://pypi.org/project/google-cloud-documentai/
- Cost **(estimate)**: 4,000 pages $6.00; 500 pages $0.75.

### C8. Anthropic Claude with PDF / image input

- Limits: "Maximum request size 32 MB", "Maximum pages per request 600 (100 when the request's
  context window is under 1M tokens)"; "The system converts each page of the document into an
  image"; "Text token costs: Each page typically uses 1,500-3,000 tokens per page depending on content
  density. Standard API pricing applies with no additional PDF fees"; image token costs also apply.
  https://platform.claude.com/docs/en/build-with-claude/pdf-support
- Images: cost `ceil(width/28) x ceil(height/28)` visual tokens; standard tier max 1568 px long edge /
  1568 tokens (Haiku 4.5, Sonnet 4.6 and earlier), high-resolution tier 2576 px / 4784 tokens (4.7+);
  "1000x1000 image costs about $1.30 USD per thousand images" on Haiku 4.5.
  https://platform.claude.com/docs/en/build-with-claude/vision
- Pricing: Haiku 4.5 $1 / $5 per MTok; Sonnet 5 $2 / $10; Opus 5 $5 / $25; Batch API 50 % off.
  https://platform.claude.com/docs/en/about-claude/pricing
- Citations: PDF citations use `page_location` with 1-indexed `start_page_number`; plain text uses
  `char_location`; "For PDFs: Text is extracted ... Citing images from PDFs is not currently
  supported" (so citations do not help on image-only scans).
  https://platform.claude.com/docs/en/build-with-claude/citations
- Cost **(estimate)**: assume a scanned page rendered to ~1,500 visual tokens plus ~700 output
  tokens of transcribed text, no text-layer tokens. Haiku 4.5: ~$0.005/page, 4,000 pages ~$20
  (batch ~$10), 500 pages ~$2.60. Sonnet 5: ~$0.010/page, ~$41 / ~$5. Opus 5 on the high-resolution
  tier could triple the image tokens.

### C9. OpenAI GPT with PDF / image input

- PDF guide: "each file must be under 50 MB. The combined limit across all files in the request is
  50 MB"; "the API extracts both text and page images and sends both to the model"; requires vision
  models (`gpt-4o` and later). No page cap stated. https://developers.openai.com/api/docs/guides/pdf-files
- Pricing: gpt-5 $1.25 / $10; gpt-5-mini $0.25 / $2.00; gpt-5-nano $0.05 / $0.40; gpt-4.1-mini
  $0.40 / $1.60; gpt-4o $2.50 / $10; batch 50 % off. https://developers.openai.com/api/docs/pricing
- Image tokens: patch-based with a per-model multiplier (gpt-5-mini 1.2); note the vision guide marks
  `gpt-5` as "Deprecated and scheduled for shutdown", so verify model availability before adopting.
  https://developers.openai.com/api/docs/guides/images-vision
- Cost **(estimate)** gpt-5-mini with the same ~1,500 in / ~700 out assumption: ~$0.002/page,
  4,000 pages ~$8 (batch ~$4), 500 pages ~$1.

---

## 4. Recommended pipeline

1. **Open with pypdfium2** (`PdfDocument(bytes_or_path)`), iterate pages 0..n-1, keep the 1-based
   page number for citations.
2. **Extract per page** with `textpage = page.get_textpage()`;
   `n = textpage.count_chars()`; text via `get_text_bounded()` (full Unicode). Store
   `(page_number, text, char_start, char_end)` where offsets are cumulative over our own
   concatenation (page texts joined with a fixed separator). Keep `get_charbox(i)` available for
   highlight boxes later; do not persist per-char boxes by default.
3. **Decide per page whether OCR is needed** (section 5).
4. **OCR fallback**: for the subset of pages flagged, either send the whole PDF once to Azure Read
   with the `pages` query parameter listing only those pages (billing is per analyzed page), or
   render flagged pages with `page.render(scale=300/72)` and send images. Prefer the `pages`
   parameter: one request, no rasterization on the VPS.
5. **Merge**: replace the flagged pages' text with the Read `content` slice for that page (Azure
   gives `spans{offset,length}` per page/word), then recompute our cumulative offsets. Keep the
   per-word `confidence` and a `source: "text-layer" | "azure-read"` flag per page for debugging.
6. **Guardrails**: cap OCR at a monthly page budget in worker config; skip OCR (and record the
   reason) when the cap is hit; retry on 429 with the `retry-after` header (Azure documents a 15 TPS
   default and a `retry-after` header on analyze responses).

## 5. "Page has no usable text" heuristic

What official sources say:

- OCRmyPDF's content-stream check sets `has_text = True` as soon as any text operator is found in
  the page's content stream, regardless of character count; its detailed (pdfminer) analysis only
  counts text boxes that intersect the interior of the page with 12.5 % margins excluded on all
  sides, and it distinguishes visible text from corrupt text represented by U+FFFD.
  https://github.com/ocrmypdf/OCRmyPDF/blob/main/src/ocrmypdf/pdfinfo/info.py
- OCRmyPDF `--skip-text` skips "pages that already have text"; `--redo-ocr` removes existing
  non-printing OCR text and re-runs OCR (relevant if a user uploads a PDF that already carries a poor
  OCR layer). https://ocrmypdf.readthedocs.io/en/latest/advanced.html
- pdfplumber states it "Works best on machine-generated, rather than scanned, PDFs".
  https://github.com/jsvine/pdfplumber
- PyMuPDF's OCR can be restricted to image areas only (`full=False`), an alternative signal that a
  page is image-dominated. https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html

No official source publishes a numeric character-count threshold. Proposed rule (own design, to be
tuned on a sample of real uploads):

```
text = textpage.get_text_bounded()
visible = [c for c in text if not c.isspace()]
bad = text.count("�")
image_area = sum(area of image objects on page) / page_area   # pypdfium2 page.get_objects()

needs_ocr = (
    len(visible) < 20                          # essentially empty text layer
    or (bad > 0 and bad / max(len(visible), 1) > 0.2)   # corrupt/garbled encoding
) and image_area > 0.5                          # page is mostly one or more images
```

Also treat a document as "already OCRed" when text exists on image-dominated pages; keep that text
(it is usually a prior OCR layer) unless the U+FFFD ratio trips, mirroring OCRmyPDF's skip/redo split.

## 6. Does a hosted OCR API make local Tesseract unnecessary?

Yes, at 20-200 documents/month. Worst case (all 4,000 pages scanned) is about $6/month on Azure
Read, Textract or Google OCR, versus the operational cost of Tesseract on a small VPS: Tesseract
peaks at "about 12 bytes per pixel" of the page image (a 300 dpi letter page is ~8.4 MP, so ~100 MB
per concurrent page, more with OCRmyPDF's pipeline) https://ocrmypdf.readthedocs.io/en/latest/performance.html ,
needs explicit `eng+fra+deu+spa` with order-dependent results
https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html , and offers no language detection
beyond the `osd` script detector https://tesseract-ocr.github.io/tessdoc/Data-Files.html . The
hosted Read model auto-detects languages and mixed-language lines
https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr .
The image-size argument for Tesseract is weak in the other direction too: the Debian packages for
the engine plus four language packs total roughly 11-15 MB, so if we ever want an offline fallback
it is cheap to add.

## 7. Open questions

1. **Azure Read price is not confirmed from the rendered official page** (it shows "$-" without
   JavaScript). Confirm $1.50 per 1,000 pages in the Azure pricing calculator for the chosen region
   before committing. Same for Google Document AI OCR ($1.50 per 1,000 from a search snippet).
2. **Azure F0 trick**: F0 gives 500 free pages/month but analyzes only the first 2 pages per request.
   Splitting flagged pages into 2-page PDFs would keep the 500-page scenario at $0. Verify this is
   acceptable use and that the 1 TPS F0 limit is tolerable for the worker.
3. **Data residency**: none of the cost figures consider EU-region pricing or residency; Azure and
   Google have regional endpoints, Mistral's docs pages did not state hosting region. Decide whether
   residency is a requirement before finalizing.
4. **LlamaParse Fast tier and scanned pages**: the tiers page says Fast is for "plain-text
   documents"; whether it OCRs image-only pages is not stated. If it does, LlamaParse's free 10K
   credits/month would cover the whole 4,000-page worst case at $0.
5. **Mistral OCR per-request limits** (file size, page count) were not on the docs pages read; only the
   512 MB upload limit is documented. The "OCR $4 / 1,000" versus "OCR (per 1K pages) $3" lines on the
   same pricing page need clarification.
6. **Docling RAM and model size** on a small VPS are not documented on the official pages read; only
   relevant if layout-aware local parsing is ever wanted.
7. **Vision-LLM cost estimates** assume ~1,500 visual tokens and ~700 output tokens per scanned page;
   measure with `count_tokens` on real pages before using an LLM for OCR.
8. **Threshold tuning**: the 20-character / 0.2 U+FFFD / 0.5 image-area values are starting points;
   validate on a labelled sample of our own uploads (text-layer, scanned, mixed, pre-OCRed).
